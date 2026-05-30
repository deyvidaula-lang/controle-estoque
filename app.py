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
    try:
        # Tenta ler a planilha e encontrar a aba correta
        xl = pd.ExcelFile(file)
        sheet_name = xl.sheet_names[0]
        if 'ABASTECER PLANILHA DE LOTES' in xl.sheet_names:
            sheet_name = 'ABASTECER PLANILHA DE LOTES'
        
        df = pd.read_excel(file, sheet_name=sheet_name)
        
        # Mapeamento flexível de colunas
        mapping = {
            'cod_principal': ['COD.', 'Cód. Principal', 'Codigo', 'Cod'],
            'descricao': ['Descrição do Produto', 'Descrição', 'Descricao', 'DESC.'],
            'cod_secundario': ['COD..1', 'Cód. Secundário', 'Secundario'],
            'local_gaveta': ['GAVETA', 'Local / Gaveta', 'Local', 'Gaveta'],
            'end_lote_torre': ['END LOTE', 'End. Lote (Torre)', 'Endereço', 'Torre'],
            'qtd_torre': ['QUNT LOTE', 'Qtd. Torre', 'Quantidade Torre', 'Qtd Torre']
        }
        
        def find_col(possible_names, df_cols):
            for name in possible_names:
                if name in df_cols: return name
                # Busca parcial e case-insensitive
                for col in df_cols:
                    if name.lower() in str(col).lower(): return col
            return None

        cols = df.columns
        mapped_cols = {key: find_col(val, cols) for key, val in mapping.items()}

        conn = sqlite3.connect('estoque.db')
        agora = datetime.now().strftime('%d/%m/%Y %H:%M')
        
        count = 0
        for _, row in df.iterrows():
            # Só importa se tiver pelo menos o código principal ou descrição
            cp = str(row.get(mapped_cols['cod_principal'], '')) if mapped_cols['cod_principal'] else ''
            ds = str(row.get(mapped_cols['descricao'], '')) if mapped_cols['descricao'] else ''
            
            if cp != 'nan' or ds != 'nan':
                conn.execute('''
                    INSERT INTO estoque (cod_principal, cod_secundario, descricao, local_gaveta, 
                    end_lote_torre, qtd_torre, abastecimento, atualizado)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    cp if cp != 'nan' else '',
                    str(row.get(mapped_cols['cod_secundario'], '')) if mapped_cols['cod_secundario'] else '',
                    ds if ds != 'nan' else '',
                    str(row.get(mapped_cols['local_gaveta'], '')) if mapped_cols['local_gaveta'] else '',
                    str(row.get(mapped_cols['end_lote_torre'], '')) if mapped_cols['end_lote_torre'] else '',
                    str(row.get(mapped_cols['qtd_torre'], '')) if mapped_cols['qtd_torre'] else '',
                    'A Abastecer',
                    agora
                ))
                count += 1
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'sucesso', 'importados': count})
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

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
