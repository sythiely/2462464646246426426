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
        self.timeout = 20
        self.delay = random.uniform(8, 15)  # Delay entre tentativas
        self.db_file = "accounts.db"
        self._init_db()
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
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
        """Gera credenciais aleatórias realísticas"""
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(6, 10)))
        password = ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*', k=12))
        email = f"{username}@{random.choice(['gmail.com', 'yahoo.com', 'outlook.com'])}"
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
        """Verificação em duas etapas da conta criada"""
        try:
            # Primeira verificação: Tentar acessar página de perfil
            response = session.get(self.profile_url, timeout=self.timeout)
            if response.status_code == 200 and username.lower() in response.text.lower():
                return True
            
            # Segunda verificação: Tentar fazer login
            response = session.get(self.login_url, timeout=self.timeout)
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            
            login_data = {
                'username': username,
                'password': password,
                'csrf_token': csrf_token
            }
            
            response = session.post(self.login_url, data=login_data, allow_redirects=False)
            
            # Verifica redirecionamento após login
            if response.status_code == 302:
                response = session.get(self.profile_url, timeout=self.timeout)
                return username.lower() in response.text.lower()
            return False
        except Exception as e:
            print(f"Erro na verificação: {str(e)}")
            return False

    def create_account(self):
        """Fluxo completo de criação de conta"""
        username, password, email = self._generate_credentials()
        session = requests.Session()
        session.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': self.register_url
        })

        try:
            # 1. Obter página de registro
            response = session.get(self.register_url, timeout=self.timeout)
            if response.status_code != 200:
                return False, username, "Falha ao carregar página de registro"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token = soup.find('input', {'name': 'csrf_token'}).get('value')
            if not csrf_token:
                return False, username, "CSRF token não encontrado"
            
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
            
            # 3. Verificar resposta
            if response.status_code != 302:
                return False, username, "Falha no registro (status inválido)"
            
            # 4. Verificação em duas etapas
            if not self._verify_account(session, username, password):
                return False, username, "Falha na verificação da conta"
            
            # 5. Salvar no banco de dados
            if not self._save_account(username, password, email):
                return False, username, "Conta já existe no banco de dados"
            
            return True, username, "Conta criada com sucesso"
            
        except Exception as e:
            return False, username, f"Erro: {str(e)}"
        finally:
            session.close()

def worker(creator, result_queue, stop_event, stats):
    """Função executada por cada thread"""
    while not stop_event.is_set():
        success, username, message = creator.create_account()
        with stats['lock']:
            if success:
                stats['created'] += 1
            else:
                stats['failed'] += 1
        result_queue.put((success, username, message))
        time.sleep(creator.delay)

def print_stats(stats):
    """Exibe estatísticas formatadas"""
    print(f"\r[✓] {stats['created']} sucessos | [x] {stats['failed']} falhas | Threads ativas: {threading.active_count()-1}", end='')

def main():
    print("=== Itch.io Account Creator ===")
    print("Iniciando criação de contas (10 threads)")
    print("Pressione Ctrl+C para parar\n")
    
    creator = ItchioAccountCreator()
    result_queue = Queue()
    stop_event = threading.Event()
    
    # Estatísticas compartilhadas
    stats = {
        'created': 0,
        'failed': 0,
        'lock': threading.Lock()
    }
    
    # Iniciar workers
    threads = []
    for i in range(10):
        t = threading.Thread(
            target=worker,
            args=(creator, result_queue, stop_event, stats),
            name=f"Worker-{i+1}"
        )
        t.daemon = True
        t.start()
        threads.append(t)
    
    # Mostrar progresso
    try:
        while True:
            success, username, message = result_queue.get()
            print_stats(stats)
            
            # Exibir detalhes ocasionalmente
            if random.random() < 0.3:  # 30% de chance de mostrar detalhes
                status = "✓" if success else "x"
                print(f"\n[{status}] {username}: {message}")
                print_stats(stats)
                
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
        
        print(f"\nResumo final:")
        print(f"- Contas criadas nesta sessão: {stats['created']}")
        print(f"- Falhas nesta sessão: {stats['failed']}")
        print(f"- Total no banco de dados: {total}")

if __name__ == "__main__":
    main()
