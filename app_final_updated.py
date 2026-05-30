import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-estoque-seguro')

# Configurações do Admin via Variáveis de Ambiente
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'deyvid.aula@gmail.com')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin0302')

def init_db():
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cod_principal TEXT,
            cod_secundario TEXT,
            descricao TEXT,
            local_gaveta TEXT,
            qtd_local TEXT,
            end_lote_torre TEXT,
            qtd_torre TEXT,
            abastecimento TEXT,
            observacao TEXT,
            atualizado TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            senha TEXT,
            role TEXT
        )
    ''')
    # Adicionar admin inicial se não existir
    cursor.execute("INSERT OR IGNORE INTO usuarios (email, senha, role) VALUES (?, ?, ?)", 
                  (ADMIN_EMAIL, ADMIN_PASSWORD, 'admin'))
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session.get('role') != 'admin':
            return jsonify({'erro': 'Acesso negado'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('password')
        
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        cursor.execute("SELECT email, role FROM usuarios WHERE email = ? AND senha = ?", (email, senha))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['user'] = user[0]
            session['role'] = user[1]
            return redirect(url_for('index'))
        return render_template('login.html', erro="E-mail ou senha incorretos")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/api/estoque', methods=['GET'])
@login_required
def get_estoque():
    conn = sqlite3.connect('estoque.db')
    df = pd.read_sql_query("SELECT * FROM estoque ORDER BY atualizado DESC", conn)
    conn.close()
    return jsonify(df.to_dict(orient='records'))

@app.route('/api/estoque', methods=['POST'])
@login_required
def update_estoque():
    data = request.json
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()
    
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    if data.get('id'):
        cursor.execute('''
            UPDATE estoque SET 
            cod_principal=?, cod_secundario=?, descricao=?, local_gaveta=?, 
            qtd_local=?, end_lote_torre=?, qtd_torre=?, abastecimento=?, 
            observacao=?, atualizado=?
            WHERE id=?
        ''', (data['cod_principal'], data['cod_secundario'], data['descricao'], 
              data['local_gaveta'], data['qtd_local'], data['end_lote_torre'], 
              data['qtd_torre'], data['abastecimento'], data['observacao'], agora, data['id']))
    else:
        cursor.execute('''
            INSERT INTO estoque (cod_principal, cod_secundario, descricao, local_gaveta, 
            qtd_local, end_lote_torre, qtd_torre, abastecimento, observacao, atualizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['cod_principal'], data['cod_secundario'], data['descricao'], 
              data['local_gaveta'], data['qtd_local'], data['end_lote_torre'], 
              data['qtd_torre'], data['abastecimento'], data['observacao'], agora))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/api/importar', methods=['POST'])
@login_required
def importar():
    if 'file' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo'}), 400
    
    file = request.files['file']
    df = pd.read_excel(file)
    
    conn = sqlite3.connect('estoque.db')
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    for _, row in df.iterrows():
        conn.execute('''
            INSERT INTO estoque (cod_principal, cod_secundario, descricao, local_gaveta, atualizado)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(row.get('Cód. Principal', '')), str(row.get('Cód. Secundário', '')), 
              str(row.get('Descrição', '')), str(row.get('Local / Gaveta', '')), agora))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    conn = sqlite3.connect('estoque.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, role FROM usuarios")
    usuarios = [{'id': r[0], 'email': r[1], 'role': r[2]} for r in cursor.fetchall()]
    conn.close()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/api/admin/usuarios', methods=['POST'])
@admin_required
def add_usuario():
    data = request.json
    conn = sqlite3.connect('estoque.db')
    try:
        conn.execute("INSERT INTO usuarios (email, senha, role) VALUES (?, ?, ?)", 
                    (data['email'], data['senha'], 'user'))
        conn.commit()
        return jsonify({'status': 'sucesso'})
    except:
        return jsonify({'erro': 'Usuário já existe'}), 400
    finally:
        conn.close()

@app.route('/api/admin/usuarios/<int:id>', methods=['DELETE'])
@admin_required
def delete_usuario(id):
    conn = sqlite3.connect('estoque.db')
    conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'sucesso'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
