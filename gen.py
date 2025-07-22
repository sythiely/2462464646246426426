import random
import string
import threading
import time
import traceback
import sqlite3
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)
DB_FILE = "users.db"
REGISTER_URL = "https://itch.io/register"
TIMEOUT = 15
threads_count = 10
creation_stop_event = threading.Event()
progress_lock = threading.Lock()
created_accounts = 0
creation_running = False

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_user_to_db(username, password, email):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)', (username, password, email))
        conn.commit()
        conn.close()
    except Exception:
        traceback.print_exc()

def generate_random_string(length, chars):
    return ''.join(random.choice(chars) for _ in range(length))

def generate_username():
    length = random.randint(6, 8)
    return generate_random_string(length, string.ascii_letters + string.digits)

def generate_password():
    return generate_random_string(8, string.ascii_letters + string.digits)

def generate_email():
    prefix = generate_random_string(5, string.ascii_lowercase + string.digits)
    domains = ["gmail.com", "outlook.com", "yahoo.com"]
    return f"{prefix}@{random.choice(domains)}"

def create_itchio_account(username, password, email):
    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
        ])
    })
    try:
        r = session.get(REGISTER_URL, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        token_input = soup.find('input', {'name': 'csrf_token', 'type': 'hidden'})
        csrf_token = token_input['value'] if token_input else None
        if not csrf_token:
            return False
        form_data = {
            "username": username,
            "password": password,
            "password_repeat": password,
            "email": email,
            "accept_terms": "1",
            "csrf_token": csrf_token,
            "submit": "Create account"
        }
        session.headers.update({'Referer': REGISTER_URL})
        post = session.post(REGISTER_URL, data=form_data, allow_redirects=False, timeout=TIMEOUT)
        if post.status_code == 302:
            location = post.headers.get('Location', '')
            if 'my-feed' in location or 'login' in location:
                return True
        return False
    except:
        return False

def worker():
    global created_accounts
    while not creation_stop_event.is_set():
        username = generate_username()
        password = generate_password()
        email = generate_email()
        success = create_itchio_account(username, password, email)
        if success:
            with progress_lock:
                created_accounts += 1
            save_user_to_db(username, password, email)
        time.sleep(random.uniform(10, 25))

@app.route('/start', methods=['POST'])
def start_creation():
    global creation_running, creation_stop_event, created_accounts
    if creation_running:
        return jsonify({"message": "Criação já em andamento"})
    creation_stop_event.clear()
    created_accounts = 0
    for _ in range(threads_count):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
    creation_running = True
    return jsonify({"message": f"Criando contas com {threads_count} threads."})

@app.route('/status')
def status():
    return jsonify({"created": created_accounts})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
