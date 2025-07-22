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

BASE_URL = "https://itch.io"
REGISTER_URL = f"{BASE_URL}/register"

DATABASE_FILE = "users.db"  # Arquivo do banco de dados SQLite
TIMEOUT = 15
DELAY_BETWEEN_ATTEMPTS = random.uniform(10, 25)

USE_PROXIES = False
PROXIES = []

request_queue = Queue()
result_queue = Queue()
creation_stop_event = threading.Event()
progress_lock = threading.Lock()

# Inicializa o banco de dados
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
        return False  # Username já existe
    except Exception as e:
        print(f"[{threading.current_thread().name}] Erro ao salvar no banco de dados: {e}")
        return False

def create_itchio_account_request(username, password, email):
    session_manager = SessionManager()
    session = session_manager.create_session()
    account_status = "FAILED"

    thread_name = threading.current_thread().name
    print(f"[{thread_name}] Tentando: {username}:{password} ({email})")

    try:
        response_get = session.get(REGISTER_URL, timeout=TIMEOUT)
        response_get.raise_for_status()

        soup = BeautifulSoup(response_get.text, 'html.parser')
        csrf_token_input = soup.find('input', {'name': 'csrf_token', 'type': 'hidden'})
        csrf_token = csrf_token_input.get('value') if csrf_token_input else None

        if not csrf_token:
            print(f"[{thread_name}] Erro: CSRF token não encontrado.")
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
                print(f"[{thread_name}] Conta '{username}' criada com sucesso.")
                account_status = "SUCCESS"
            else:
                print(f"[{thread_name}] Redirecionamento inesperado: {redirect_location}")
                account_status = "FAILED_REDIRECT"
        else:
            print(f"[{thread_name}] Falha no POST, status: {response_post.status_code}")
            account_status = "FAILED_POST"

    except Exception as e:
        print(f"[{thread_name}] Erro: {e}")
        traceback.print_exc()
        account_status = "FAILED_UNKNOWN"

    return account_status

def account_generation_worker():
    while not creation_stop_event.is_set():
        try:
            username = generate_username()
            password = generate_password()
            email = generate_email()

            status = create_itchio_account_request(username, password, email)

            with progress_lock:
                if status == "SUCCESS":
                    save_to_database(username, password, email)
                    result_queue.put("SUCCESS")
                else:
                    result_queue.put("FAILED")
        except Exception as e:
            print(f"[{threading.current_thread().name}] ERRO: {e}")
            traceback.print_exc()
            result_queue.put("FAILED")
        finally:
            time.sleep(random.uniform(DELAY_BETWEEN_ATTEMPTS, DELAY_BETWEEN_ATTEMPTS * 1.5))

def start_generation():
    init_db()  # Garante que o banco de dados está criado
    
    print("\nIniciando gerador de contas Itch.io (10 threads, criação infinita)")
    print("Pressione Ctrl+C para parar.\n")

    threads = []
    for i in range(10):  # 10 threads fixas
        t = threading.Thread(target=account_generation_worker, name=f"Worker-{i+1}")
        t.daemon = True
        t.start()
        threads.append(t)

    created_count = 0
    failed_count = 0

    try:
        while True:
            try:
                status = result_queue.get(timeout=0.5)
                if status == "SUCCESS":
                    created_count += 1
                else:
                    failed_count += 1
                print(f"\rContas criadas: {created_count} | Falhas: {failed_count}", end='', flush=True)
                result_queue.task_done()
            except Empty:
                if all(not t.is_alive() for t in threads):
                    break
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nInterrupção detectada. Parando...")
        creation_stop_event.set()
    finally:
        for t in threads:
            if t.is_alive():
                t.join(timeout=5)

        print(f"\n\nProcesso concluído: {created_count} contas válidas, {failed_count} falhas.")
        print(f"Contas salvas no banco de dados: {DATABASE_FILE}")

if __name__ == "__main__":
    start_generation()
