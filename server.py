from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
import threading
import time
import random
import string
from database import AccountDatabase
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Instância do banco de dados
db = AccountDatabase()

# Variáveis globais de controle
creation_active = False
following_active = False
creation_thread = None
following_thread = None
target_user_global = ""

# Estatísticas em tempo real
real_time_stats = {
    'accounts_created_session': 0,
    'follows_made_session': 0,
    'creation_rate': 0,
    'follow_rate': 0,
    'last_created_account': '',
    'last_follow_action': ''
}

def generate_random_string(length, chars):
    return ''.join(random.choice(chars) for _ in range(length))

def generate_account_data():
    """Gera dados aleatórios para uma conta"""
    username_prefixes = ['user', 'gamer', 'dev', 'player', 'creator', 'indie', 'game', 'pixel', 'code', 'art']
    username = random.choice(username_prefixes) + str(random.randint(100, 9999))
    password = 'pass' + generate_random_string(6, string.ascii_letters + string.digits)
    
    domains = ['gmail.com', 'outlook.com', 'yahoo.com', 'hotmail.com', 'protonmail.com']
    email = f"{username.lower()}{random.randint(1, 99)}@{random.choice(domains)}"
    
    return username, password, email

def account_creation_worker():
    """Worker thread para criação de contas"""
    global creation_active, real_time_stats
    
    print("[SISTEMA] Thread de criação iniciada")
    
    while creation_active:
        try:
            # Simula tempo de criação (2-5 segundos)
            time.sleep(random.uniform(2, 5))
            
            if not creation_active:
                break
                
            # Gera dados da conta
            username, password, email = generate_account_data()
            
            # Simula processo de criação (90% de sucesso)
            if random.random() < 0.9:
                # Adiciona ao banco
                if db.add_account(username, password, email):
                    real_time_stats['accounts_created_session'] += 1
                    real_time_stats['last_created_account'] = f"{username}:{password}"
                    print(f"[CRIAÇÃO] Conta criada: {username}")
                else:
                    print(f"[CRIAÇÃO] Erro ao salvar conta: {username}")
            else:
                print(f"[CRIAÇÃO] Falha na criação da conta: {username}")
                
        except Exception as e:
            print(f"[CRIAÇÃO] Erro no worker: {e}")
            time.sleep(1)
    
    print("[SISTEMA] Thread de criação finalizada")

def following_worker():
    """Worker thread para sistema de seguidores"""
    global following_active, real_time_stats, target_user_global
    
    print(f"[SISTEMA] Thread de seguidores iniciada - Alvo: {target_user_global}")
    
    while following_active and target_user_global:
        try:
            # Busca contas ativas
            active_accounts = db.get_active_accounts()
            
            if not active_accounts:
                print("[SEGUIDOR] Nenhuma conta ativa disponível")
                time.sleep(5)
                continue
            
            # Seleciona uma conta aleatória
            username, password = random.choice(active_accounts)
            
            # Simula tempo de follow (1-3 segundos)
            time.sleep(random.uniform(1, 3))
            
            if not following_active:
                break
            
            # Simula processo de follow (85% de sucesso)
            success = random.random() < 0.85
            
            if success:
                db.add_follow_activity(username, target_user_global, success=True)
                db.update_account_usage(username, success=True)
                real_time_stats['follows_made_session'] += 1
                real_time_stats['last_follow_action'] = f"{username} → {target_user_global}"
                print(f"[SEGUIDOR] {username} seguiu {target_user_global}")
            else:
                db.add_follow_activity(username, target_user_global, success=False, error_message="Falha simulada")
                db.update_account_usage(username, success=False)
                print(f"[SEGUIDOR] Falha: {username} → {target_user_global}")
                
        except Exception as e:
            print(f"[SEGUIDOR] Erro no worker: {e}")
            time.sleep(2)
    
    print("[SISTEMA] Thread de seguidores finalizada")

@app.route('/')
def index():
    """Página principal"""
    with open('index.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/api/stats')
def get_stats():
    """Retorna estatísticas atualizadas"""
    db_stats = db.get_statistics()
    
    # Combina estatísticas do banco com as da sessão atual
    combined_stats = {
        **db_stats,
        **real_time_stats,
        'creation_active': creation_active,
        'following_active': following_active,
        'target_user': target_user_global,
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify(combined_stats)

@app.route('/api/accounts')
def get_accounts():
    """Retorna lista de contas"""
    accounts = db.get_all_accounts()
    
    account_list = []
    for account in accounts[-20:]:  # Últimas 20 contas
        account_list.append({
            'username': account[0],
            'password': account[1],
            'email': account[2] or 'N/A',
            'created_date': account[3],
            'is_active': bool(account[4]),
            'login_count': account[5]
        })
    
    return jsonify({'accounts': account_list})

@app.route('/api/creation/start', methods=['POST'])
def start_creation():
    """Inicia criação de contas"""
    global creation_active, creation_thread
    
    if not creation_active:
        creation_active = True
        creation_thread = threading.Thread(target=account_creation_worker, daemon=True)
        creation_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Criação de contas iniciada',
            'active': True
        })
    else:
        return jsonify({
            'status': 'info',
            'message': 'Criação já está ativa',
            'active': True
        })

@app.route('/api/creation/stop', methods=['POST'])
def stop_creation():
    """Para criação de contas"""
    global creation_active
    
    creation_active = False
    
    return jsonify({
        'status': 'success',
        'message': 'Criação de contas parada',
        'active': False
    })

@app.route('/api/following/start', methods=['POST'])
def start_following():
    """Inicia sistema de seguidores"""
    global following_active, following_thread, target_user_global
    
    data = request.get_json()
    target_user = data.get('target_user', '').strip()
    
    if not target_user:
        return jsonify({
            'status': 'error',
            'message': 'Usuário alvo é obrigatório'
        })
    
    if not following_active:
        target_user_global = target_user
        following_active = True
        following_thread = threading.Thread(target=following_worker, daemon=True)
        following_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'Sistema de seguidores iniciado para: {target_user}',
            'active': True,
            'target_user': target_user
        })
    else:
        return jsonify({
            'status': 'info',
            'message': 'Sistema de seguidores já está ativo',
            'active': True,
            'target_user': target_user_global
        })

@app.route('/api/following/stop', methods=['POST'])
def stop_following():
    """Para sistema de seguidores"""
    global following_active, target_user_global
    
    following_active = False
    target_user_global = ""
    
    return jsonify({
        'status': 'success',
        'message': 'Sistema de seguidores parado',
        'active': False
    })

@app.route('/api/export', methods=['GET'])
def export_accounts():
    """Exporta contas para arquivo"""
    try:
        filename = f"accounts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        db.export_accounts_to_file(filename)
        
        return jsonify({
            'status': 'success',
            'message': f'Contas exportadas para: {filename}',
            'filename': filename
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Erro ao exportar: {str(e)}'
        })

@app.route('/api/reset', methods=['POST'])
def reset_system():
    """Reset completo do sistema"""
    global creation_active, following_active, real_time_stats, target_user_global
    
    # Para todos os processos
    creation_active = False
    following_active = False
    target_user_global = ""
    
    # Reset estatísticas da sessão
    real_time_stats = {
        'accounts_created_session': 0,
        'follows_made_session': 0,
        'creation_rate': 0,
        'follow_rate': 0,
        'last_created_account': '',
        'last_follow_action': ''
    }
    
    return jsonify({
        'status': 'success',
        'message': 'Sistema resetado com sucesso'
    })

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Gerencia configurações do sistema"""
    if request.method == 'GET':
        configs = {
            'threads_count': db.get_config('threads_count'),
            'max_accounts': db.get_config('max_accounts'),
            'delay_between_actions': db.get_config('delay_between_actions'),
            'success_threshold': db.get_config('success_threshold')
        }
        return jsonify(configs)
    
    elif request.method == 'POST':
        data = request.get_json()
        
        for key, value in data.items():
            if key in ['threads_count', 'max_accounts', 'delay_between_actions', 'success_threshold']:
                db.set_config(key, str(value))
        
        return jsonify({
            'status': 'success',
            'message': 'Configurações salvas'
        })

if __name__ == '__main__':
    print("=== Itch.io Account Manager - Servidor Backend ===")
    print("Inicializando banco de dados...")
    
    # Verifica se o arquivo HTML existe
    if not os.path.exists('index.html'):
        print("ERRO: Arquivo index.html não encontrado!")
        print("Certifique-se de salvar o código HTML como 'index.html' no mesmo diretório.")
        exit(1)
    
    # Adiciona algumas contas de teste se o banco estiver vazio
    stats = db.get_statistics()
    if stats['total_accounts'] == 0:
        print("Adicionando contas de teste...")
        test_accounts = [
            ("testuser1", "testpass1", "test1@email.com"),
            ("testuser2", "testpass2", "test2@email.com"),
            ("testuser3", "testpass3", "test3@email.com")
        ]
        
        for username, password, email in test_accounts:
            db.add_account(username, password, email)
    
    print(f"Banco inicializado com {stats['total_accounts']} contas")
    print("\nServidor iniciando...")
    print("Acesse: http://localhost:5000")
    print("Pressione Ctrl+C para parar")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
    except KeyboardInterrupt:
        print("\nServidor finalizado pelo usuário")
        creation_active = False
        following_active = False
