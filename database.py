import sqlite3
import datetime
import os
from typing import List, Tuple, Optional

class AccountDatabase:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicializa o banco de dados com as tabelas necessárias"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela principal de contas
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used DATETIME,
            is_active BOOLEAN DEFAULT 1,
            login_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            notes TEXT
        )
        ''')
        
        # Tabela de atividades de follow
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS follow_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            target_user TEXT NOT NULL,
            action_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN DEFAULT 1,
            error_message TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        # Tabela de estatísticas diárias
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE UNIQUE NOT NULL,
            accounts_created INTEGER DEFAULT 0,
            follows_made INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            active_accounts INTEGER DEFAULT 0
        )
        ''')
        
        # Tabela de configurações do sistema
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Inserir configurações padrão
        cursor.execute('''
        INSERT OR IGNORE INTO system_config (key, value) VALUES 
        ('threads_count', '10'),
        ('max_accounts', '0'),
        ('delay_between_actions', '2'),
        ('success_threshold', '95'),
        ('last_backup', ''),
        ('auto_follow_enabled', '0')
        ''')
        
        conn.commit()
        conn.close()
        print(f"Banco de dados inicializado: {self.db_path}")
    
    def add_account(self, username: str, password: str, email: str = None) -> bool:
        """Adiciona uma nova conta ao banco"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO accounts (username, password, email) 
            VALUES (?, ?, ?)
            ''', (username, password, email))
            
            # Atualizar estatísticas do dia
            today = datetime.date.today()
            cursor.execute('''
            INSERT OR REPLACE INTO daily_stats (date, accounts_created, follows_made, success_rate, active_accounts)
            VALUES (?, 
                COALESCE((SELECT accounts_created FROM daily_stats WHERE date = ?), 0) + 1,
                COALESCE((SELECT follows_made FROM daily_stats WHERE date = ?), 0),
                COALESCE((SELECT success_rate FROM daily_stats WHERE date = ?), 0),
                COALESCE((SELECT active_accounts FROM daily_stats WHERE date = ?), 0) + 1
            )
            ''', (today, today, today, today, today))
            
            conn.commit()
            conn.close()
            print(f"Conta adicionada: {username}")
            return True
            
        except sqlite3.IntegrityError:
            print(f"Erro: Conta {username} já existe!")
            return False
        except Exception as e:
            print(f"Erro ao adicionar conta: {e}")
            return False
    
    def get_all_accounts(self) -> List[Tuple]:
        """Retorna todas as contas do banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT username, password, email, created_date, is_active, login_count 
        FROM accounts 
        ORDER BY created_date DESC
        ''')
        
        accounts = cursor.fetchall()
        conn.close()
        return accounts
    
    def get_active_accounts(self) -> List[Tuple]:
        """Retorna apenas contas ativas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT username, password FROM accounts 
        WHERE is_active = 1 
        ORDER BY last_used ASC, login_count ASC
        ''')
        
        accounts = cursor.fetchall()
        conn.close()
        return accounts
    
    def update_account_usage(self, username: str, success: bool = True):
        """Atualiza informações de uso da conta"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE accounts 
        SET last_used = CURRENT_TIMESTAMP, 
            login_count = login_count + 1,
            success_rate = CASE 
                WHEN login_count = 0 THEN CASE WHEN ? THEN 100.0 ELSE 0.0 END
                ELSE (success_rate * login_count + CASE WHEN ? THEN 100.0 ELSE 0.0 END) / (login_count + 1)
            END
        WHERE username = ?
        ''', (success, success, username))
        
        conn.commit()
        conn.close()
    
    def add_follow_activity(self, username: str, target_user: str, success: bool = True, error_message: str = None):
        """Registra atividade de follow"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Buscar ID da conta
        cursor.execute('SELECT id FROM accounts WHERE username = ?', (username,))
        account_row = cursor.fetchone()
        
        if not account_row:
            conn.close()
            return False
        
        account_id = account_row[0]
        
        cursor.execute('''
        INSERT INTO follow_activities (account_id, target_user, success, error_message)
        VALUES (?, ?, ?, ?)
        ''', (account_id, target_user, success, error_message))
        
        # Atualizar estatísticas do dia
        today = datetime.date.today()
        cursor.execute('''
        INSERT OR REPLACE INTO daily_stats (date, accounts_created, follows_made, success_rate, active_accounts)
        VALUES (?, 
            COALESCE((SELECT accounts_created FROM daily_stats WHERE date = ?), 0),
            COALESCE((SELECT follows_made FROM daily_stats WHERE date = ?), 0) + 1,
            COALESCE((SELECT success_rate FROM daily_stats WHERE date = ?), 95.0),
            (SELECT COUNT(*) FROM accounts WHERE is_active = 1)
        )
        ''', (today, today, today, today))
        
        conn.commit()
        conn.close()
        return True
    
    def get_statistics(self) -> dict:
        """Retorna estatísticas completas do sistema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Estatísticas gerais
        cursor.execute('SELECT COUNT(*) FROM accounts')
        total_accounts = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM accounts WHERE is_active = 1')
        active_accounts = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM follow_activities')
        total_follows = cursor.fetchone()[0]
        
        cursor.execute('''
        SELECT COUNT(*) FROM accounts 
        WHERE DATE(created_date) = DATE('now')
        ''')
        today_created = cursor.fetchone()[0]
        
        cursor.execute('''
        SELECT COUNT(*) FROM follow_activities 
        WHERE DATE(action_date) = DATE('now')
        ''')
        today_follows = cursor.fetchone()[0]
        
        cursor.execute('''
        SELECT AVG(success_rate) FROM accounts 
        WHERE login_count > 0
        ''')
        avg_success_rate = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_accounts': total_accounts,
            'active_accounts': active_accounts,
            'total_follows': total_follows,
            'today_created': today_created,
            'today_follows': today_follows,
            'success_rate': round(avg_success_rate, 1)
        }
    
    def deactivate_account(self, username: str) -> bool:
        """Desativa uma conta"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE accounts SET is_active = 0 WHERE username = ?
            ''', (username,))
            
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Erro ao desativar conta: {e}")
            return False
    
    def get_daily_stats(self, days: int = 7) -> List[dict]:
        """Retorna estatísticas dos últimos dias"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT date, accounts_created, follows_made, success_rate, active_accounts
        FROM daily_stats 
        WHERE date >= DATE('now', '-{} days')
        ORDER BY date DESC
        '''.format(days))
        
        rows = cursor.fetchall()
        conn.close()
        
        stats = []
        for row in rows:
            stats.append({
                'date': row[0],
                'accounts_created': row[1],
                'follows_made': row[2],
                'success_rate': row[3],
                'active_accounts': row[4]
            })
        
        return stats
    
    def export_accounts_to_file(self, filename: str = "accounts_backup.txt") -> bool:
        """Exporta todas as contas para arquivo"""
        try:
            accounts = self.get_all_accounts()
            with open(filename, 'w', encoding='utf-8') as f:
                for account in accounts:
                    username, password = account[0], account[1]
                    f.write(f"{username}:{password}\n")
            
            print(f"Contas exportadas para: {filename}")
            return True
        except Exception as e:
            print(f"Erro ao exportar: {e}")
            return False
    
    def import_accounts_from_file(self, filename: str) -> int:
        """Importa contas de um arquivo"""
        imported = 0
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        username, password = line.split(':', 1)
                        if self.add_account(username, password):
                            imported += 1
            
            print(f"Contas importadas: {imported}")
            return imported
        except Exception as e:
            print(f"Erro ao importar: {e}")
            return 0
    
    def cleanup_old_activities(self, days: int = 30):
        """Remove atividades antigas para otimizar o banco"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        DELETE FROM follow_activities 
        WHERE action_date < DATE('now', '-{} days')
        '''.format(days))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"Atividades antigas removidas: {deleted}")
        return deleted
    
    def get_config(self, key: str) -> str:
        """Obtém valor de configuração"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM system_config WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def set_config(self, key: str, value: str):
        """Define valor de configuração"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR REPLACE INTO system_config (key, value, updated_date)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, value))
        
        conn.commit()
        conn.close()

# Exemplo de uso e testes
if __name__ == "__main__":
    # Criar instância do banco
    db = AccountDatabase()
    
    print("=== Teste do Sistema de Banco de Dados ===")
    
    # Adicionar algumas contas de teste
    test_accounts = [
        ("user123", "pass123", "user123@gmail.com"),
        ("gamer456", "pass456", "gamer456@outlook.com"),
        ("dev789", "pass789", "dev789@yahoo.com"),
        ("player001", "pass001", "player001@gmail.com"),
        ("creator002", "pass002", "creator002@outlook.com")
    ]
    
    print("\n1. Adicionando contas de teste...")
    for username, password, email in test_accounts:
        db.add_account(username, password, email)
    
    print("\n2. Listando todas as contas:")
    accounts = db.get_all_accounts()
    for account in accounts:
        print(f"  {account[0]}:{account[1]} - Criada: {account[3]} - Ativa: {account[4]}")
    
    print("\n3. Simulando atividades de follow...")
    active_accounts = db.get_active_accounts()
    for i, (username, password) in enumerate(active_accounts[:3]):
        target = f"target_user_{i+1}"
        db.add_follow_activity(username, target, success=True)
        db.update_account_usage(username, success=True)
        print(f"  {username} seguiu {target}")
    
    print("\n4. Estatísticas do sistema:")
    stats = db.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n5. Exportando contas para arquivo...")
    db.export_accounts_to_file("accounts_export.txt")
    
    print("\n6. Configurações do sistema:")
    configs = ['threads_count', 'max_accounts', 'delay_between_actions']
    for config in configs:
        value = db.get_config(config)
        print(f"  {config}: {value}")
    
    print("\n7. Limpeza de atividades antigas...")
    cleaned = db.cleanup_old_activities(30)
    
    print("\n=== Banco de dados configurado e testado com sucesso! ===")
    print(f"Arquivo do banco: {db.db_path}")
    print("O sistema está pronto para uso.")
