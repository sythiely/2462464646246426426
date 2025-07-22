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
LOGIN_URL = f"{BASE_URL}/login"
PROFILE_URL = f"{BASE_URL}/my-feed"

DATABASE_FILE = "users.db"
TIMEOUT = 15
DELAY_BETWEEN_ATTEMPTS = random.uniform(10, 25)

class AccountCreator:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"
        ]
        self.init_db()

    def init_db(self):
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

    def create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        })
        return session

    def generate_account(self):
        username = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        email = f"{username}@example.com"
        return username, password, email

    def save_account(self, username, password, email):
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO accounts (username, password, email) VALUES (?, ?, ?)",
                     (username, password, email))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def verify_account(self, session, username):
        try:
            # Verifica se consegue acessar a página de perfil
            response = session.get(PROFILE_URL, timeout=TIMEOUT)
            if response.status_code == 200 and username.lower() in response.text.lower():
                return True
            
            # Tenta fazer login para confirmar
            response = session.get(LOGIN_URL, timeout=TIMEOUT)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            
            login_data = {
                'username': username,
                'password': password,
                'csrf_token': csrf_token
            }
            
            response = session.post(LOGIN_URL, data=login_data, allow_redirects=False)
            return response.status_code == 302
        except:
            return False

    def create_account(self):
        username, password, email = self.generate_account()
        session = self.create_session()
        
        try:
            # Passo 1: Obter página de registro e CSRF token
            response = session.get(REGISTER_URL, timeout=TIMEOUT)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            
            # Passo 2: Enviar formulário de registro
            form_data = {
                'username': username,
                'password': password,
                'password_repeat': password,
                'email': email,
                'accept_terms': '1',
                'csrf_token': csrf_token
            }
            
            response = session.post(REGISTER_URL, data=form_data, allow_redirects=False)
            
            # Passo 3: Verificar se foi realmente criada
            if response.status_code == 302:
                if self.verify_account(session, username):
                    self.save_account(username, password, email)
                    return True, username
        except Exception as e:
            print(f"Erro: {str(e)}")
        
        return False, username

def worker(creator, result_queue, stop_event):
    while not stop_event.is_set():
        success, username = creator.create_account()
        result_queue.put(('SUCCESS' if success else 'FAIL', username))
        time.sleep(DELAY_BETWEEN_ATTEMPTS)

def main():
    print("=== Itch.io Account Creator ===")
    print("Iniciando criação de contas (10 threads)")
    print("Pressione Ctrl+C para parar\n")
    
    creator = AccountCreator()
    result_queue = Queue()
    stop_event = threading.Event()
    
    # Iniciar workers
    threads = []
    for i in range(10):
        t = threading.Thread(
            target=worker,
            args=(creator, result_queue, stop_event),
            name=f"Worker-{i+1}"
        )
        t.daemon = True
        t.start()
        threads.append(t)
    
    # Mostrar progresso
    created = 0
    failed = 0
    
    try:
        while True:
            status, username = result_queue.get()
            if status == 'SUCCESS':
                created += 1
                print(f"\r[✓] {username} | Válidas: {created} | Falhas: {failed}", end='')
            else:
                failed += 1
                print(f"\r[x] {username} | Válidas: {created} | Falhas: {failed}", end='')
    except KeyboardInterrupt:
        print("\n\nParando threads...")
        stop_event.set()
        for t in threads:
            t.join(timeout=1)
        
        # Mostrar resumo final
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM accounts")
        total = c.fetchone()[0]
        conn.close()
        
        print(f"\nContas criadas nesta sessão: {created}")
        print(f"Total no banco de dados: {total}")

if __name__ == "__main__":
    main()
