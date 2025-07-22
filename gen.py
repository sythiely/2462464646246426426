import requests
import threading
import time
import random
import string
import sqlite3
from bs4 import BeautifulSoup

class ItchioAccountCreator:
    def __init__(self):
        self.base_url = "https://itch.io"
        self.register_url = f"{self.base_url}/register"
        self.login_url = f"{self.base_url}/login"
        self.profile_url = f"{self.base_url}/my-feed"
        self.timeout = 15
        self.delay = random.uniform(5, 10)
        self.db_file = "users.db"
        self._init_db()
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"
        ]

    def _init_db(self):
        """Inicializa o banco de dados SQLite"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS accounts
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT UNIQUE,
                     password TEXT,
                     email TEXT,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()

    def _generate_credentials(self):
        """Gera credenciais aleatórias"""
        username = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        email = f"{username}@example.com"
        return username, password, email

    def _save_account(self, username, password, email):
        """Salva a conta no banco de dados"""
        try:
            conn = sqlite3.connect(self.db_file)
            c = conn.cursor()
            c.execute("INSERT INTO accounts (username, password, email) VALUES (?, ?, ?)",
                     (username, password, email))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Username já existe
        finally:
            conn.close()

    def _verify_account(self, session, username, password):
        """Verifica se a conta foi realmente criada"""
        try:
            # Tentativa de login para verificação
            response = session.get(self.login_url, timeout=self.timeout)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            
            login_data = {
                'username': username,
                'password': password,
                'csrf_token': csrf_token
            }
            
            response = session.post(self.login_url, data=login_data, allow_redirects=False)
            
            # Verifica se o login foi bem-sucedido
            if response.status_code == 302:
                response = session.get(self.profile_url, timeout=self.timeout)
                return username.lower() in response.text.lower()
            return False
        except:
            return False

    def create_account(self):
        """Tenta criar uma conta no itch.io"""
        username, password, email = self._generate_credentials()
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        })

        try:
            # 1. Obter página de registro e CSRF token
            response = session.get(self.register_url, timeout=self.timeout)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            
            # 2. Enviar formulário de registro
            form_data = {
                'username': username,
                'password': password,
                'password_repeat': password,
                'email': email,
                'accept_terms': '1',
                'csrf_token': csrf_token
            }
            
            response = session.post(self.register_url, data=form_data, allow_redirects=False)
            
            # 3. Verificar se a conta foi realmente criada
            if response.status_code == 302:
                if self._verify_account(session, username, password):
                    if self._save_account(username, password, email):
                        return True, username
            return False, username
        except Exception as e:
            return False, username
        finally:
            session.close()

def worker(creator, result_queue, stop_event):
    """Função executada por cada thread"""
    while not stop_event.is_set():
        success, username = creator.create_account()
        result_queue.put(('SUCCESS' if success else 'FAIL', username))
        time.sleep(creator.delay)

def main():
    print("=== Itch.io Account Creator ===")
    print("Iniciando criação de contas (10 threads)")
    print("Pressione Ctrl+C para parar\n")
    
    creator = ItchioAccountCreator()
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
        conn = sqlite3.connect(creator.db_file)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM accounts")
        total = c.fetchone()[0]
        conn.close()
        
        print(f"\nContas criadas nesta sessão: {created}")
        print(f"Total no banco de dados: {total}")

if __name__ == "__main__":
    main()
