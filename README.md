# AI Counselor Chatbot - User Manual

## Overview
This AI Counselor Chatbot is a secure web application that provides conversational AI services with speech recognition and text-to-speech capabilities. The application features user authentication, session management, and encrypted data storage.

## Demo of th software
[Watch the demo video by clicking here](https://www.youtube.com/watch?v=gLxJVUZX6qg)

## Prerequisites
Before installation, ensure your system has:
1. Python 3.9+
2. Ollama installed (https://ollama.com/download)
3. FFmpeg installed (`sudo apt install ffmpeg` for Ubuntu/Debian)
4. Git (`sudo apt install git` for Ubuntu/Debian)

## Installation Guide

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/ai-counselor-chatbot.git
cd ai-counselor-chatbot
```

### 2. Create and Activate Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Install Required Packages
```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables
Create a `.env` file in the project root:
```env
SECRET_KEY=your_secure_secret_key_here
```

### 5. Download Required AI Models
```bash
ollama pull gemma3:latest
```

### 6. Generate SSL Certificates (Optional but Recommended)
```bash
mkdir keys
openssl req -x509 -newkey rsa:4096 -nodes -out keys/cert.pem -keyout keys/key.pem -days 365
```

### 7. Initialize the Database
```bash
python -c "from app import init_db; init_db()"
```

## Running the Application

### Start the Application
```bash
python app.py
```

### Access the Application
1. Open your web browser to: `https://localhost:5000`
2. Bypass SSL warning (click "Advanced" → "Proceed to localhost")

## First-Time Setup

### Create Admin Account
1. Visit `https://localhost:5000`
2. Click "Register"
3. Enter a username and password
4. Click "Register" button

### Customize AI Personality
Edit the `admin_prompt_conv.txt` file to modify the AI's personality. For example:
```text
You are an academic counselor for engineering aspirants. Your role is to:
- Collect student information (name, phone, HSC marks, JEE percentile)
- Provide guidance on engineering admissions
- Maintain a professional yet friendly tone
```

## Using the Chatbot

### 1. Login
- Enter your credentials
- Click "Login"

### 2. Start a Session
- Click the microphone icon to begin speaking, on by default.
- Wait for the AI response (audio will play automatically)

### 3. Conversation Flow
- The AI will guide the conversation to collect information
- Speak naturally after the AI has stopped speaking, it will listen for upto 6 seconds before sending response to the server.

### 4. Ending a Session
- Click "Save and Close" to securely save the conversation, and then logout.
- Your data will be encrypted and stored.

## Security Features
1. **Data Encryption**: All user data is encrypted using Fernet encryption
2. **Secure Sessions**: Automatic session expiration after 30 minutes
3. **Password Hashing**: Passwords are hashed with Werkzeug security
4. **SSL Encryption**: Built-in HTTPS support for secure communication

## Troubleshooting

### Common Issues & Solutions
**Problem**: Ollama connection errors  
**Solution**: Ensure Ollama is running: `ollama serve`

**Problem**: Audio not working  
**Solution**: 
1. Check browser microphone permissions
2. Verify FFmpeg installation with `ffmpeg -version`

**Problem**: SSL certificate errors  
**Solution**: 
1. Delete existing keys in `/keys`
2. Regenerate certificates using Step 6 in Installation

**Problem**: Database initialization errors  
**Solution**:
```bash
rm conversation_history.db
touch conversation_history.db
python -c "from app import init_db; init_db()"
```

## Maintenance

### Backing Up Data
Database and audio files are stored in:
- `conversation_history.db` (SQLite database)
- `/audio_logs` (conversation recordings)

### Updating AI Model
To use a different model:
1. Edit `app.py`:
```python
OLLAMA_MODEL = 'your-new-model-here'
```
2. Download the new model:
```bash
ollama pull your-new-model-here
```
