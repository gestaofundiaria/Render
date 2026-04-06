import hashlib
import hmac
import os
from datetime import timedelta
from time import time

from flask import Flask, abort, jsonify, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOGIN_MAX_TENTATIVAS = 5
LOGIN_TEMPO_BLOQUEIO_SEGUNDOS = 120
ITERACOES_HASH = 600_000
ARQUIVOS_PROTEGIDOS = {'teste.geojson', 'arq.qgz', 'teste.qmd'}
PAGINAS_PRINCIPAIS = ('index.html', 'gestores.html')

USUARIOS = {
    'caio': {
        'salt': '4685401b3ca48700f9b2277665cf7b34',
        'hash': '1c64c23fabd91d791616e77c728cf9595649fec16d4ecbc9da420e72f2db1f7a'
    },
    'claudia': {
        'salt': '4288a86c07ba1defe8cf373602de790e',
        'hash': '4d6ac3ecb3c2dae5923dd925a9456b642966ce4b0dc930fa0d774bd1fb9c3a18'
    },
    'michele': {
        'salt': 'e053357dc3acfdcbad3d20136fb076eb',
        'hash': '7030c3d80e98eb91e70fb477afe74d431305afd6d976c82109a28758e572479e'
    },
    'melissa': {
        'salt': '0186d12aeae88bc9186595d558679136',
        'hash': 'e36ddf36d43344caa25ddc538263b95b2b9edac5eacd575c6259cd2f71a0bbcd'
    },
    'roger': {
        'salt': '4a5924dd83eafc8dc7196cc66adad324',
        'hash': '34becc0175342fc59a25c6d1a4769b01df7df016a373f82a4bf69cd979623e50'
    }
}

tentativas_por_chave = {}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
_cookie_secure_padrao = '1' if (os.environ.get('RENDER') or os.environ.get('RENDER_EXTERNAL_URL')) else '0'
app.config.update(
    SECRET_KEY=os.environ.get('GESTORES_SECRET_KEY') or os.urandom(32).hex(),
    SESSION_COOKIE_NAME='gestao_fundiaria_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('GESTORES_COOKIE_SECURE', _cookie_secure_padrao).strip().lower() in {'1', 'true', 'yes', 'on'},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)


def normalizar_usuario(usuario):
    return str(usuario or '').strip().lower()


def obter_chave_cliente(usuario):
    forwarded = request.headers.get('X-Forwarded-For', '')
    ip = forwarded.split(',')[0].strip() or request.remote_addr or 'local'
    return f'{ip}:{normalizar_usuario(usuario)}'


def gerar_hash_credencial(usuario, senha, salt):
    conteudo = str(senha or '').encode('utf-8')
    return hashlib.pbkdf2_hmac('sha256', conteudo, salt.encode('utf-8'), ITERACOES_HASH).hex()


def credencial_valida(usuario, senha):
    registro = USUARIOS.get(normalizar_usuario(usuario))
    if not registro:
        return False

    hash_calculado = gerar_hash_credencial(usuario, senha, registro['salt'])
    return hmac.compare_digest(hash_calculado, registro['hash'])


def tempo_restante_bloqueio(chave):
    registro = tentativas_por_chave.get(chave)
    if not registro:
        return 0

    bloqueado_ate = float(registro.get('bloqueado_ate') or 0)
    restante = int(round(bloqueado_ate - time()))
    if restante <= 0:
        tentativas_por_chave.pop(chave, None)
        return 0

    return restante


def registrar_falha(chave):
    registro = tentativas_por_chave.setdefault(chave, {'tentativas': 0, 'bloqueado_ate': 0})
    registro['tentativas'] = int(registro.get('tentativas') or 0) + 1

    if registro['tentativas'] >= LOGIN_MAX_TENTATIVAS:
        registro['tentativas'] = 0
        registro['bloqueado_ate'] = time() + LOGIN_TEMPO_BLOQUEIO_SEGUNDOS
        return {
            'blocked': True,
            'remainingAttempts': 0,
            'retryAfter': LOGIN_TEMPO_BLOQUEIO_SEGUNDOS,
        }

    registro['bloqueado_ate'] = 0
    return {
        'blocked': False,
        'remainingAttempts': max(0, LOGIN_MAX_TENTATIVAS - registro['tentativas']),
        'retryAfter': 0,
    }


def limpar_tentativas(chave):
    tentativas_por_chave.pop(chave, None)


@app.after_request
def aplicar_cabecalhos_sem_cache(response):
    caminho = os.path.basename(request.path or '')
    if request.path.startswith('/api/') or caminho in ARQUIVOS_PROTEGIDOS:
        response.headers['Cache-Control'] = 'no-store'
    return response


def obter_pagina_principal():
    for nome_arquivo in PAGINAS_PRINCIPAIS:
        if os.path.isfile(os.path.join(BASE_DIR, nome_arquivo)):
            return nome_arquivo
    abort(404)


@app.get('/')
def raiz():
    return send_from_directory(BASE_DIR, obter_pagina_principal())


@app.get('/api/session')
def api_session():
    usuario = session.get('usuario')
    return jsonify({
        'authenticated': bool(usuario),
        'usuario': usuario,
    })


@app.post('/api/login')
def api_login():
    dados = request.get_json(silent=True) or request.form.to_dict() or {}
    usuario = normalizar_usuario(dados.get('usuario'))
    senha = str(dados.get('senha') or '')

    if not usuario or not senha:
        return jsonify({
            'authenticated': False,
            'message': 'Informe usuário e senha.',
        }), 400

    chave = obter_chave_cliente(usuario)
    restante = tempo_restante_bloqueio(chave)
    if restante > 0:
        return jsonify({
            'authenticated': False,
            'message': f'Acesso temporariamente bloqueado. Tente novamente em {restante}s.',
            'retryAfter': restante,
            'remainingAttempts': 0,
        }), 429

    if not credencial_valida(usuario, senha):
        falha = registrar_falha(chave)
        if falha['blocked']:
            return jsonify({
                'authenticated': False,
                'message': f'Muitas tentativas inválidas. Tente novamente em {falha["retryAfter"]}s.',
                'retryAfter': falha['retryAfter'],
                'remainingAttempts': 0,
            }), 429

        return jsonify({
            'authenticated': False,
            'message': 'Usuário ou senha incorretos.',
            'remainingAttempts': falha['remainingAttempts'],
        }), 401

    session.clear()
    session.permanent = True
    session['usuario'] = usuario
    limpar_tentativas(chave)

    return jsonify({
        'authenticated': True,
        'usuario': usuario,
        'message': 'Acesso autorizado. Carregando mapa...',
    })


@app.post('/api/logout')
def api_logout():
    session.clear()
    return jsonify({
        'authenticated': False,
        'message': 'Sessão encerrada.',
    })


@app.route('/<path:filename>')
def servir_arquivo(filename):
    caminho_normalizado = os.path.normpath(filename).replace('\\', '/')
    if caminho_normalizado.startswith('../'):
        abort(404)

    nome_base = os.path.basename(caminho_normalizado)

    if nome_base in PAGINAS_PRINCIPAIS:
        return send_from_directory(BASE_DIR, obter_pagina_principal())

    if nome_base in ARQUIVOS_PROTEGIDOS and not session.get('usuario'):
        return jsonify({
            'authenticated': False,
            'message': 'Faça login para acessar este recurso.',
        }), 401

    caminho_completo = os.path.join(BASE_DIR, caminho_normalizado)
    if not os.path.isfile(caminho_completo):
        abort(404)

    return send_from_directory(BASE_DIR, caminho_normalizado)


if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    app.run(host=host, port=port, debug=False)
