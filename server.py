from flask import Flask, jsonify, request
import sqlite3
import threading
import random
import string
import time
import requests
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder='.', static_url_path='')

# Configurações
DATABASE = "users.db"
WORKER_THREADS = 10
active_threads = []
stop_flag = False
session_count = 0
lock = threading.Lock()

# Inicializa o banco de dados
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  email TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

# Gera dados aleatórios
def generate_account():
    username = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    email = f"{username}@example.com"
    return username, password, email

# Tenta criar uma conta
def create_account():
    global session_count
    
    username, password, email = generate_account()
    
    try:
        # Simula a criação da conta (substitua pela lógica real)
        # Para teste, vamos apenas adicionar ao banco de dados
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT INTO accounts (username, password, email) VALUES (?, ?, ?)",
                  (username, password, email))
        conn.commit()
        conn.close()
        
        with lock:
            session_count += 1
        return True
    except sqlite3.IntegrityError:
        # Username já existe
        return False
    except Exception as e:
        print(f"Erro: {e}")
        return False

# Função que roda em cada thread
def worker():
    while not stop_flag:
        if create_account():
            time.sleep(random.uniform(1, 3))  # Delay entre contas
        else:
            time.sleep(0.5)

# Rotas da API
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/start', methods=['POST'])
def start():
    global active_threads, stop_flag, session_count
    
    # Reseta o contador e a flag
    with lock:
        session_count = 0
    stop_flag = False
    
    # Inicia as threads
    active_threads = []
    for _ in range(WORKER_THREADS):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        active_threads.append(t)
    
    return jsonify({"success": True})

@app.route('/stop', methods=['POST'])
def stop():
    global stop_flag
    stop_flag = True
    return jsonify({"success": True})

@app.route('/get_stats')
def get_stats():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM accounts")
    total = c.fetchone()[0]
    conn.close()
    
    with lock:
        return jsonify({
            "total": total,
            "session": session_count
        })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
