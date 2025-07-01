import os
import requests
from dotenv import load_dotenv
from cs50 import SQL
import json
import datetime
from datetime import timedelta
import tempfile
import edge_tts
import asyncio
from cryptography.fernet import Fernet
import nest_asyncio
import speech_recognition as sr
import threading
import ffmpeg
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash

# Apply nest_asyncio to allow asyncio event loops to be nested
nest_asyncio.apply()
load_dotenv()

# --- SSL Configuration ---
cert_path = os.path.join(os.path.dirname(__file__), 'keys', 'cert.pem')
key_path = os.path.join(os.path.dirname(__file__), 'keys', 'key.pem')
ssl_context = None
if cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path):
    ssl_context = (cert_path, key_path)

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
app.permanent_session_lifetime = timedelta(minutes=30)

# --- LLM Configuration ---
OLLAMA_URL = 'http://localhost:11434/api/chat'
OLLAMA_MODEL = 'gemma3:latest'

# --- Directory and File Paths ---
AUDIO_LOG_DIR = os.path.join(os.path.dirname(__file__), 'audio_logs')
KEY_FILE = os.path.join(os.path.dirname(__file__), 'keys', 'secret.key')
DB_FILE = "sqlite:///conversation_history.db"
os.makedirs(AUDIO_LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)

# --- Database Setup ---
def init_db():
    db = SQL(DB_FILE)
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hash TEXT NOT NULL
        );
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS Main (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            info_json TEXT,
            start_time TEXT,
            end_time TEXT,
            duration TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    ''')
    db._disconnect()

# Initialize the database on startup
init_db()

# --- Fernet Key Management ---
def load_or_create_key():
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
    else:
        with open(KEY_FILE, 'rb') as f:
            key = f.read()
    return key

fernet = Fernet(load_or_create_key())

# --- Admin Prompt Loading ---
try:
    with open("admin_prompt_conv.txt", 'r') as f:
        admin_prompt = f.read()
except FileNotFoundError:
    admin_prompt = "You are a helpful assistant."

# --- Helper functions ---
def safe_filename(who):
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return f"{timestamp}_{who}.wav"

async def generate_speech_bytes(text):
    try:
        communicate = edge_tts.Communicate(text=text, voice="en-IN-NeerjaNeural")
        tts_audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == 'audio':
                tts_audio_bytes += chunk["data"]
        return tts_audio_bytes
    except Exception as e:
        print(f"Error generating speech: {e}")
        return b""

# --- Data Extraction ---
def extract_user_data(conversation_history):
    print("Summarizing User Data with Local Ollama")
    data = { 'name': None, 'phone': None, 'hsc_marks': None, 'jee_percentile': None }

    def query_ollama_for_info(prompt_for_extraction, context_messages):
        try:
            payload = {
                'model': OLLAMA_MODEL,
                'messages': context_messages + [{'role' : 'user', 'content' : prompt_for_extraction}],
                'stream': False, 'options': {'temperature': 0.0}
            }
            llm_resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            llm_resp.raise_for_status()
            return llm_resp.json()['message']['content'].strip()
        except requests.exceptions.RequestException as e:
            print(f"Error querying Ollama: {e}")
            return "None"

    try:
        with open("admin_prompt_extr.txt", 'r') as f:
            extraction_system_prompt = f.read()
    except FileNotFoundError:
        extraction_system_prompt = "You are an expert data extractor. From the conversation history, extract only the specific information requested. Output 'None' if the information is not present."

    extraction_context = [{'role': 'system', 'content': extraction_system_prompt}] + conversation_history

    data['name'] = query_ollama_for_info('What is the full name of the user?', extraction_context)
    data['phone'] = query_ollama_for_info('What is the mobile number of the user?', extraction_context)
    data['hsc_marks'] = query_ollama_for_info('What are the HSC/12th percentage of the user?', extraction_context)
    data['jee_percentile'] = query_ollama_for_info('What is the JEE Percentile of the user?', extraction_context)
    return data

# --- Routes and Core Logic ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('login_signup.html')

@app.route('/auth', methods=['POST'])
def auth():
    session.clear()
    username = request.form.get("username")
    password = request.form.get("password")
    action = request.form.get("action")

    if not username or not password:
        flash("Username and password are required.", "error")
        return redirect(url_for('index'))

    db = SQL(DB_FILE)
    try:
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if action == 'register':
            if rows:
                flash("Username already exists. Please choose another or log in.", "error")
                return redirect(url_for('index'))
            hash_pass = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash_pass)
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('index'))

        elif action == 'login':
            if not rows or not check_password_hash(rows[0]["hash"], password):
                flash("Invalid username or password.", "error")
                return redirect(url_for('index'))
            
            session.permanent = True
            session['user_id'] = rows[0]["id"]
            session['username'] = rows[0]["username"]
            return redirect(url_for('chat'))
        else:
            flash("Invalid action.", "error")
            return redirect(url_for('index'))
    finally:
        db._disconnect()

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('main.html', username=session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))

@app.route('/initiate', methods=['POST'])
def initiate():
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    
    session['conversation_history'] = []
    session['audio_paths'] = []
    session['initial_time'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return asyncio.get_event_loop().run_until_complete(start_chat())

async def start_chat():
    user_id = session.get('user_id')
    db = SQL(DB_FILE)
    try:
        data_rows = db.execute("SELECT info_json FROM Main WHERE user_id = ?", user_id)
    finally:
        db._disconnect()

    initiate_prompt = f"Hi {session.get('username')}, how may I help you today?"
    if data_rows and data_rows[0]['info_json']:
        try:
            decrypted_data = fernet.decrypt(data_rows[0]['info_json']).decode('utf-8')
            user_info = json.loads(decrypted_data)
            initiate_prompt = f"You're connected to an existing user: {session.get('username')}. Current info: {user_info}. Your tone should be warm and friendly. Start with a personalized, professional greeting. Do not list all details unless necessary. Begin."
        except Exception as e:
            print(f"Error decrypting data for user {user_id}: {e}")
            initiate_prompt = f"Hi {session.get('username')}, I had some trouble retrieving your previous information, but I'm here to help. How can I assist you today?"
            
    conversation_history = session.get('conversation_history', [])
    prompt = [{'role' : 'system', 'content' : admin_prompt}, {'role' : 'user', 'content' : initiate_prompt}]
    
    try:
        payload = {'model': OLLAMA_MODEL, 'messages': prompt, 'stream': False}
        llm_resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        llm_resp.raise_for_status()
        reply_text = llm_resp.json()['message']['content']
    except requests.exceptions.RequestException as e:
        print(f"Ollama API error on initiation: {e}")
        reply_text = "I'm sorry, I'm having trouble connecting right now. Please try again in a moment."

    conversation_history.append({'role':'assistant','content':reply_text})
    
    bot_wav_name = safe_filename('bot')
    bot_wav_path = os.path.join(AUDIO_LOG_DIR, bot_wav_name)
    tts_audio_bytes = await generate_speech_bytes(reply_text)

    if tts_audio_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tf:
            tf.write(tts_audio_bytes)
            temp_mp3_path = tf.name
        try:
            ffmpeg.input(temp_mp3_path).output(bot_wav_path, ar=16000, ac=1).overwrite_output().run(capture_stdout=True, capture_stderr=True)
            audio_paths = session.get('audio_paths', [])
            audio_paths.append(bot_wav_path)
            session['audio_paths'] = audio_paths
        except ffmpeg.Error as e:
            print(f"FFMPEG error: {e.stderr.decode()}")
        finally:
            if os.path.exists(temp_mp3_path):
                 os.remove(temp_mp3_path)
    else:
        bot_wav_name = None # No audio to play

    session['conversation_history'] = conversation_history
    return jsonify({'reply_text': reply_text, 'reply_audio_url': f'/reply_audio/{bot_wav_name}' if bot_wav_name else ''})

@app.route('/speech', methods=['POST'])
def speech_path():
    if 'user_id' not in session:
        return jsonify({"error": "Not authenticated"}), 401
    return asyncio.get_event_loop().run_until_complete(speech())

async def speech():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file found"}), 400

    audio = request.files['audio']
    
    # --- Start of Changes ---
    
    # 1. Define a permanent path for the user's audio
    user_wav_name = safe_filename('user')
    user_wav_path = os.path.join(AUDIO_LOG_DIR, user_wav_name)
    
    # Get the current audio paths from the session
    audio_paths = session.get('audio_paths', [])

    temp_webm_path = None
    try:
        # Save incoming audio to a temporary webm file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_webm:
            audio.save(temp_webm.name)
            temp_webm_path = temp_webm.name

        # Convert the temporary webm to our permanent wav file
        ffmpeg.input(temp_webm_path).output(user_wav_path, ar=16000, ac=1).overwrite_output().run(capture_stdout=True, capture_stderr=True)
        
        # 2. Add the new user audio path to our list for later processing
        audio_paths.append(user_wav_path)
        session['audio_paths'] = audio_paths # Save it back to the session

        # Now, use the newly created file for speech recognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(user_wav_path) as source:
            audio_data = recognizer.record(source)
            user_text = recognizer.recognize_google(audio_data, language='en-US')

    # --- End of Changes ---

    except sr.UnknownValueError:
        user_text = '(User audio was empty or indecipherable)'
    except sr.RequestError as e:
        user_text = '(Speech recognition service failed)'
        print(f"Google Speech API error: {e}")
    except ffmpeg.Error as e:
        print(f"FFMPEG error during conversion: {e.stderr.decode()}")
        # If conversion fails, remove the failed user audio path from the list
        if user_wav_path in audio_paths:
            audio_paths.remove(user_wav_path)
            session['audio_paths'] = audio_paths
        return jsonify({"error": "Failed to process audio"}), 500
    except Exception as e:
        print(f"An unexpected error occurred during speech recognition: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500
    finally:
        # We only need to clean up the temporary webm file now
        if temp_webm_path and os.path.exists(temp_webm_path):
             os.remove(temp_webm_path)
    
    # The rest of the function remains the same...
    conversation_history = session.get('conversation_history', [])
    conversation_history.append({'role':'user', 'content': user_text})
    prompt = [{'role' : 'system', 'content' : admin_prompt}] + conversation_history
    
    reply_text = 'Sorry, there was an error with the local LLM.'
    try:
        payload = {'model': OLLAMA_MODEL, 'messages': prompt, 'stream': False}
        llm_resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        llm_resp.raise_for_status()
        reply_text = llm_resp.json()['message']['content']
    except requests.requests.exceptions.RequestException as e:
        print(f"Ollama API error: {e}")

    conversation_history.append({'role':'assistant','content':reply_text})
    
    bot_wav_name = safe_filename('bot')
    bot_wav_path = os.path.join(AUDIO_LOG_DIR, bot_wav_name)
    tts_audio_bytes = await generate_speech_bytes(reply_text)

    if tts_audio_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tf:
            tf.write(tts_audio_bytes)
            temp_mp3_path = tf.name
        try:
            ffmpeg.input(temp_mp3_path).output(bot_wav_path, ar=16000, ac=1).overwrite_output().run(capture_stdout=True, capture_stderr=True)
            # This is where the bot's audio path is added
            audio_paths = session.get('audio_paths', [])
            audio_paths.append(bot_wav_path)
            session['audio_paths'] = audio_paths
        except ffmpeg.Error as e:
            print(f"FFMPEG error creating bot audio: {e.stderr.decode()}")
        finally:
            if os.path.exists(temp_mp3_path): os.remove(temp_mp3_path)
    else:
        bot_wav_name = None

    session['conversation_history'] = conversation_history
    return jsonify({
        'user_text': user_text, 'reply_text': reply_text,
        'reply_audio_url': f'/reply_audio/{bot_wav_name}' if bot_wav_name else ''
    })

@app.route('/reply_audio/<filename>')
def reply_audio(filename):
    file_path = os.path.join(AUDIO_LOG_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='audio/wav')
    else:
        return jsonify({"error": "File not found"}), 404

def process_and_save_conversation(app_context, conversation_history, audio_paths, initial_time_str, user_id):
    with app_context:
        print(f"Background thread started for user_id: {user_id}")
        if not conversation_history:
            print("No conversation to save.")
            return

        try:
            if audio_paths:
                # --- Create a directory for the silence file ---
                tmp_dir = os.path.join(os.path.dirname(__file__), 'silence')
                os.makedirs(tmp_dir, exist_ok=True)
                silence_path = os.path.join(tmp_dir, 'silence.wav')

                # --- ** NEW: Generate the silent audio file if it doesn't exist ** ---
                if not os.path.exists(silence_path):
                    print("Generating silence.wav...")
                    try:
                        # FIXED: Use correct parameter for silence duration
                        ffmpeg.input('anullsrc', format='lavfi').output(
                            silence_path, t=0.5, ar=16000, ac=1
                        ).overwrite_output().run(capture_stdout=True, capture_stderr=True)
                    except ffmpeg.Error as e:
                        print(f"Failed to generate silence file: {e.stderr.decode()}")
                        # If silence generation fails, we cannot proceed with concatenation
                        return
                
                # --- Proceed with concatenation ---
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as f_list:
                    for idx, path in enumerate(audio_paths):
                        if os.path.exists(path):
                            # Add a silent gap before every clip except the first one
                            if idx > 0:
                                f_list.write(f"file '{silence_path}'\n")
                            f_list.write(f"file '{path}'\n")
                    filelist_path = f_list.name

                if os.path.getsize(filelist_path) > 0:
                    final_wav_name = safe_filename('final')
                    final_path = os.path.join(AUDIO_LOG_DIR, final_wav_name)
                    
                    try:
                        ffmpeg.input(
                            filelist_path, format='concat', safe=0
                        ).output(
                            final_path, ar=16000, ac=1
                        ).overwrite_output().run(capture_stdout=True, capture_stderr=True)
                        print("Audio files merged successfully.")
                    except ffmpeg.Error as e:
                        print(f"Error during audio concatenation: {e.stderr.decode()}")

                    os.remove(filelist_path)
                    for path in audio_paths:
                        if os.path.exists(path):
                            os.remove(path)
                    print("Temporary audio files cleaned up.")
                else:
                    print("File list was empty. Skipping concatenation.")

        except Exception as e:
            print(f'Error during audio processing in background thread: {e}')

        # --- Data Extraction and Database Saving (Unchanged) ---
        try:
            print("Extracting user data in background thread.")
            user_data = extract_user_data(conversation_history)
            
            db = SQL(DB_FILE)
            try:
                initial_time = datetime.datetime.fromisoformat(initial_time_str)
                end_time = datetime.datetime.now(datetime.timezone.utc)
                duration = (end_time - initial_time).total_seconds()

                rows = db.execute("SELECT info_json FROM Main WHERE user_id = ?", user_id)
                json_data = {}
                if rows and rows[0]['info_json']:
                    try:
                        decrypted = fernet.decrypt(rows[0]['info_json'])
                        json_data = json.loads(decrypted.decode('utf-8'))
                    except Exception as e:
                        print(f"Could not decrypt/parse existing data for UID {user_id}: {e}")
                
                for k, v in user_data.items():
                    if v and v.strip().lower() not in ['none', '']:
                        json_data[k] = v

                if not json_data:
                    print("No new data extracted, nothing to save.")
                    return

                json_str = json.dumps(json_data)
                encrypted_json = fernet.encrypt(json_str.encode('utf-8'))
                now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

                if rows:
                    db.execute('UPDATE Main SET duration = ?, info_json = ?, start_time = ?, end_time = ?, updated_at = ? WHERE user_id = ?',
                               str(duration), encrypted_json, initial_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), now_str, user_id)
                else:
                    db.execute('INSERT INTO Main (user_id, info_json, start_time, end_time, duration, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                               user_id, encrypted_json, initial_time.strftime('%Y-%m-%d %H:%M:%S'), end_time.strftime('%Y-%m-%d %H:%M:%S'), str(duration), now_str)

                print(f"Conversation history saved to database for user_id: {user_id}.")
            finally:
                db._disconnect()
        except Exception as e:
            print(f"Error during database operation in background thread: {e}")

@app.route('/cleanup', methods=['POST'])
def cleanup():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "User not logged in"}), 401

    print("Cleanup route called. Starting background processing.")
    
    conversation_history = session.get('conversation_history', []).copy()
    initial_time = session.get('initial_time')
    user_id = session.get('user_id')
    audio_paths = session.get('audio_paths', []).copy()  # FIX: Create a copy of audio paths

    if conversation_history and initial_time and user_id and audio_paths:
        background_task = threading.Thread(
            target=process_and_save_conversation,
            args=(app.app_context(), conversation_history, audio_paths, initial_time, user_id)
        )
        background_task.start()
    else:
        print("Cleanup skipped: no conversation history to save.")

    # DO NOT DELETE AUDIO FILES HERE - background thread handles deletion
    session.pop('audio_paths', None)
    session.pop('conversation_history', None)
    session.pop('initial_time', None)
    
    return jsonify({"status": "Cleanup process started and session cleared."})

# --- Main Execution ---
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000, 
        debug=False, 
        threaded=True,
        ssl_context=ssl_context
    )