from flask import Flask, request, jsonify
from werkzeug.serving import run_simple
import sqlite3
import threading
import random
import string
import time
import requests
from bs4 import BeautifulSoup
from queue import Queue, Empty

app = Flask(__name__, static_folder='.', static_url_path='')

BASE_URL = "https://itch.io"
REGISTER_URL = f"{BASE_URL}/register"
DATABASE_FILE = "users.db"

# Variáveis globais para controle
creation_stop_event = threading.Event()
request_queue = Queue()
session_created = 0
session_lock = threading.Lock()

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  email TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def generate_username():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))

def generate_password():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))

def generate_email():
    return f"{''.join(random.choice(string.ascii_lowercase) for _ in range(8))}@example.com"

def create_account():
    global session_created
    
    username = generate_username()
    password = generate_password()
    email = generate_email()
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Obter CSRF token
        response = session.get(REGISTER_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
        
        # Enviar formulário
        data = {
            'username': username,
            'password': password,
            'password_repeat': password,
            'email': email,
            'accept_terms': '1',
            'csrf_token': csrf_token,
            'submit': 'Create account'
        }
        
        response = session.post(REGISTER_URL, data=data, allow_redirects=False)
        
        if response.status_code == 302:
            # Sucesso - salvar no banco de dados
            conn = sqlite3.connect(DATABASE_FILE)
            c = conn.cursor()
            try:
                c.execute("INSERT INTO accounts (username, password, email) VALUES (?, ?, ?)",
                          (username, password, email))
                conn.commit()
                with session_lock:
                    session_created += 1
                return True
            except sqlite3.IntegrityError:
                # Username já existe
                return False
            finally:
                conn.close()
        return False
    except Exception as e:
        print(f"Erro ao criar conta: {e}")
        return False

def worker():
    while not creation_stop_event.is_set():
        try:
            request_queue.get_nowait()
            if create_account():
                request_queue.task_done()
            else:
                # Recoloca na fila se falhou
                request_queue.put(True)
        except Empty:
            break
        time.sleep(random.uniform(5, 15))

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/start_generation', methods=['POST'])
def start_generation():
    global session_created, request_queue
    
    # Resetar contador da sessão
    with session_lock:
        session_created = 0
    
    # Limpar fila e adicionar 100 itens (número arbitrário)
    request_queue = Queue()
    for _ in range(100):
        request_queue.put(True)
    
    # Iniciar 10 workers
    creation_stop_event.clear()
    for _ in range(10):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
    
    return jsonify({'status': 'started'})

@app.route('/stop_generation', methods=['POST'])
def stop_generation():
    creation_stop_event.set()
    return jsonify({'status': 'stopped'})

@app.route('/get_stats', methods=['GET'])
def get_stats():
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM accounts")
    total = c.fetchone()[0]
    conn.close()
    
    with session_lock:
        return jsonify({
            'total_accounts': total,
            'session_created': session_created
        })

if __name__ == '__main__':
    init_db()
    run_simple('localhost', 5000, app)
