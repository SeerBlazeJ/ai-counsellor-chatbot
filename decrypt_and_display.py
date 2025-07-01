import os
import json
import sqlite3
from cryptography.fernet import Fernet

# Define the database path and key file path
# These paths are relative to the script's location
DB_PATH = os.path.join(os.path.dirname(__file__), 'conversation_history.db')
KEY_FILE = os.path.join(os.path.dirname(__file__), 'keys', 'secret.key')

def load_key():
    """
    Loads the encryption key from the specified key file.
    """
    try:
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Key file not found at {KEY_FILE}. "
              "Please ensure 'secret.key' exists in the 'keys' directory.")
        exit(1)
    except Exception as e:
        print(f"Error loading encryption key: {e}")
        exit(1)

def decrypt_data(enc_data, fernet):
    """
    Decrypts the given encrypted data using the Fernet instance.
    Returns the decoded string or an error message if decryption fails.
    """
    try:
        return fernet.decrypt(enc_data).decode('utf-8')
    except Exception as e:
        # Catch specific decryption errors for better reporting
        if "InvalidToken" in str(e):
            return f"[Decryption failed: Invalid or tampered token. Key might be wrong or data corrupted.]"
        return f"[Decryption failed: {e}]"

def main():
    """
    Main function to connect to the database, decrypt, and display user data.
    It now joins with the 'users' table to show usernames.
    """
    # Load the encryption key
    key = load_key()
    fernet = Fernet(key)

    conn = None # Initialize conn to None for finally block
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DB_PATH)
        # Set the row_factory to sqlite3.Row to access columns by name
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # SQL query to select data from 'Main' and join with 'users' to get the username.
        # We use aliases (M for Main, U for users) for clarity.
        cur.execute('''
            SELECT
                M.id,
                U.username,
                M.user_id,
                M.info_json,
                M.start_time,
                M.end_time,
                M.duration,
                M.updated_at
            FROM Main AS M
            JOIN users AS U ON M.user_id = U.id
            ORDER BY M.id ASC
        ''')
        rows = cur.fetchall()

        if not rows:
            print('No records found in the Main table.')
            return

        print("--- Decrypted User Data ---")
        for row in rows:
            print(f"\nRecord ID: {row['id']}")
            print(f"  User ID: {row['user_id']}")
            print(f"  Username: {row['username']}") # Display the fetched username
            print(f"  Conversation Start: {row['start_time']}")
            print(f"  Conversation End: {row['end_time']}")
            print(f"  Duration: {row['duration']} seconds")
            print(f"  Last Updated: {row['updated_at']}")

            # Decrypt the info_json column
            decrypted_raw = decrypt_data(row['info_json'], fernet)

            try:
                # Attempt to parse the decrypted string as JSON
                data = json.loads(decrypted_raw)
                print("  Extracted User Info:")
                # Iterate and print each key-value pair from the JSON
                for k, v in data.items():
                    print(f"    - {k}: {v}")
            except json.JSONDecodeError:
                # If decryption was successful but parsing failed (e.g., not valid JSON)
                print(f"  Decrypted Info (not valid JSON): {decrypted_raw}")
            except Exception as e:
                # Catch any other unexpected errors during processing
                print(f"  Error processing info_json: {e}")
                print(f"  Decrypted Info (raw): {decrypted_raw}")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Ensure the database connection is closed
        if conn:
            conn.close()
            print("\nDatabase connection closed.")

if __name__ == '__main__':
    main()
