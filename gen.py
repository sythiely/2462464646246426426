import requests
import threading
import time
from queue import Queue, Empty
from bs4 import BeautifulSoup
import random
import string
import os
import traceback
import sqlite3
from flask import Flask, request, jsonify
from werkzeug.serving import run_simple

app = Flask(__name__)

BASE_URL = "https://itch.io"
REGISTER_URL = f"{BASE_URL}/register"

DATABASE_FILE = "users.db"
ACCOUNTS_FILE = "accounts.txt"

TIMEOUT = 15
DELAY_BETWEEN_ATTEMPTS = random.uniform(10, 25)

USE_PROXIES = False
PROXIES = []

request_queue = Queue()
result_queue = Queue()
creation_stop_event = threading.Event()
progress_lock = threading.Lock()

# Inicializar banco de dados
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

class SessionManager:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
        ]

    def create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'
        })
        if USE_PROXIES and PROXIES:
            proxy = random.choice(PROXIES)
            session.proxies.update({
                'http': proxy,
                'https': proxy,
            })
        return session

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

def save_to_database(username, password, email):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO accounts (username, password, email) VALUES (?, ?, ?)",
                  (username, password, email))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Username já existe
        return False
    except Exception as e:
        print(f"Erro ao salvar no banco de dados: {e}")
        return False

def save_to_file(filename, data, mode="a"):
    try:
        with open(filename, mode, encoding="utf-8") as f:
            f.write(data + "\n")
    except Exception as e:
        print(f"[{threading.current_thread().name}] Erro ao salvar em {filename}: {e}")
        traceback.print_exc()

def create_itchio_account_request(username, password, email):
    session_manager = SessionManager()
    session = session_manager.create_session()
    account_status = "FAILED"

    thread_name = threading.current_thread().name
    message = f"[{thread_name}] Tentando: {username}:{password} ({email})"
    print(message)
    send_output(message)

    try:
        response_get = session.get(REGISTER_URL, timeout=TIMEOUT)
        response_get.raise_for_status()

        soup = BeautifulSoup(response_get.text, 'html.parser')
        csrf_token_input = soup.find('input', {'name': 'csrf_token', 'type': 'hidden'})
        csrf_token = csrf_token_input.get('value') if csrf_token_input else None

        if not csrf_token:
            message = f"[{thread_name}] Erro: CSRF token não encontrado."
            print(message)
            send_output(message)
            return account_status

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
        response_post = session.post(REGISTER_URL, data=form_data, allow_redirects=False, timeout=TIMEOUT)

        if response_post.status_code == 302:
            redirect_location = response_post.headers.get('Location', '')
            if 'my-feed' in redirect_location or 'login' in redirect_location:
                message = f"[{thread_name}] Conta '{username}' criada com sucesso."
                print(message)
                send_output(message)
                account_status = "SUCCESS"
            else:
                message = f"[{thread_name}] Redirecionamento inesperado: {redirect_location}"
                print(message)
                send_output(message)
                account_status = "FAILED_REDIRECT"
        else:
            message = f"[{thread_name}] Falha no POST, status: {response_post.status_code}"
            print(message)
            send_output(message)
            account_status = "FAILED_POST"

    except Exception as e:
        message = f"[{thread_name}] Erro: {e}"
        print(message)
        send_output(message)
        traceback.print_exc()
        account_status = "FAILED_UNKNOWN"

    return account_status

def account_generation_worker():
    while not creation_stop_event.is_set():
        try:
            request_queue.get_nowait()
        except Empty:
            break

        try:
            username = generate_username()
            password = generate_password()
            email = generate_email()

            status = create_itchio_account_request(username, password, email)

            with progress_lock:
                if status == "SUCCESS":
                    save_to_database(username, password, email)
                    save_to_file(ACCOUNTS_FILE, f"{username}:{password}")
                    result_queue.put("SUCCESS")
                else:
                    result_queue.put("FAILED")
        except Exception as e:
            print(f"[{threading.current_thread().name}] ERRO: {e}")
            traceback.print_exc()
            result_queue.put("FAILED")
        finally:
            request_queue.task_done()
            time.sleep(random.uniform(DELAY_BETWEEN_ATTEMPTS, DELAY_BETWEEN_ATTEMPTS * 1.5))

def account_gen_mode(thread_count, target_accounts_count, use_proxies):
    global USE_PROXIES, PROXIES
    
    USE_PROXIES = use_proxies
    if USE_PROXIES and os.path.exists("proxies.txt"):
        with open("proxies.txt", "r", encoding="utf-8") as f:
            PROXIES = [line.strip() for line in f if line.strip()]
        print(f"Proxies carregados: {len(PROXIES)}")
        send_output(f"Proxies carregados: {len(PROXIES)}")
    else:
        USE_PROXIES = False

    for _ in range(target_accounts_count * thread_count * 5):
        request_queue.put(None)

    message = f"\nIniciando gerador de contas Itch.io (Meta: {target_accounts_count} contas válidas).\nPressione Ctrl+C para parar.\n"
    print(message)
    send_output(message)

    threads = []
    for i in range(thread_count):
        t = threading.Thread(target=account_generation_worker, name=f"Worker-{i+1}")
        t.daemon = True
        t.start()
        threads.append(t)

    created_count = 0
    failed_count = 0

    while created_count < target_accounts_count and not creation_stop_event.is_set():
        try:
            status = result_queue.get(timeout=0.5)
            if status == "SUCCESS":
                created_count += 1
            else:
                failed_count += 1
            update_stats(created_count, failed_count)
            result_queue.task_done()
        except Empty:
            if request_queue.empty() and all(not t.is_alive() for t in threads):
                creation_stop_event.set()
                message = "\nTodas as threads finalizaram. Saindo."
                print(message)
                send_output(message)
                break
            time.sleep(0.1)
        except KeyboardInterrupt:
            message = "\nInterrupção detectada. Parando..."
            print(message)
            send_output(message)
            creation_stop_event.set()
            break

    message = f"\n\nProcesso concluído: {created_count} contas válidas, {failed_count} falhas."
    print(message)
    send_output(message)
    for t in threads:
        if t.is_alive():
            t.join(timeout=5)

def get_total_accounts():
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM accounts")
    total = c.fetchone()[0]
    conn.close()
    return total

def send_output(message):
    # Esta função será usada para enviar mensagens para o frontend
    pass

def update_stats(created, failed):
    # Esta função será usada para atualizar estatísticas no frontend
    pass

# Rotas Flask
@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/start_generation', methods=['POST'])
def start_generation():
    data = request.json
    thread_count = int(data.get('threads', 5))
    target_accounts_count = int(data.get('accounts', 10))
    use_proxies = data.get('use_proxies', False)
    
    creation_stop_event.clear()
    
    gen_thread = threading.Thread(
        target=account_gen_mode,
        args=(thread_count, target_accounts_count, use_proxies)
    )
    gen_thread.daemon = True
    gen_thread.start()
    
    return jsonify({'status': 'started'})

@app.route('/stop_generation', methods=['POST'])
def stop_generation():
    creation_stop_event.set()
    return jsonify({'status': 'stopped'})

@app.route('/get_stats', methods=['GET'])
def get_stats():
    total = get_total_accounts()
    return jsonify({'total_accounts': total})

if __name__ == '__main__':
    init_db()
    run_simple('localhost', 5000, app)
