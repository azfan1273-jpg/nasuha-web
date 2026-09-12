import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config.supabase_config import supabase
from routes.analytics import analytics_bp
from routes.clay_engine import clay_bp

frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))

app = Flask(__name__, static_folder=frontend_folder, static_url_path='')
CORS(app)

@app.route('/api/check-env', methods=['GET'])
def check_env():
    url = os.environ.get('SUPABASE_URL', 'KOSONG / TIDAK TERBACA')
    key = os.environ.get('SUPABASE_KEY', 'KOSONG / TIDAK TERBACA')
    return jsonify({
        'supabase_url_vercel': url,
        'supabase_key_length': len(key),
        'supabase_key_preview': key[:10] + '...' if key else 'KOSONG'
    }), 200

# Register Blueprints
app.register_blueprint(analytics_bp, url_prefix='/api')
app.register_blueprint(clay_bp, url_prefix='/api/clay')

# Endpoint Login untuk Frontend Web
# Biarkan support dua-duanya (/login dan /api/login)
@app.route('/login', methods=['GET', 'POST'])
@app.route('/api/login', methods=['GET', 'POST'])
@app.route('/login/', methods=['GET', 'POST'])
@app.route('/api/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return jsonify({'message': 'Endpoint login aktif'}), 200

    try:
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email dan password wajib diisi'}), 400

        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if res.user and res.session:
            return jsonify({
                'status': 'success',
                'access_token': res.session.access_token,
                'user': {'id': res.user.id, 'email': res.user.email}
            }), 200
        else:
            return jsonify({'error': 'Email atau password salah / tidak terdaftar'}), 401

    except Exception as e:
        err_str = str(e).lower()
        if 'invalid login credentials' in err_str or 'user_not_found' in err_str or '401' in err_str:
            return jsonify({'error': 'Email atau password salah / tidak terdaftar'}), 401
        
        return jsonify({'error': f'Gagal login: {str(e)}'}), 400
                
# Route Frontend Web Static
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
