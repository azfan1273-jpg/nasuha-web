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
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email dan password wajib diisi'}), 400

        # Memanggil auth Supabase
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        return jsonify({
            'message': 'Login berhasil',
            'user': response.user.dict() if hasattr(response.user, 'dict') else str(response.user),
            'session': response.session.dict() if hasattr(response.session, 'dict') else None
        }), 200

    except Exception as e:
        # Menangkap error 401 dari Supabase Auth
        return jsonify({'error': str(e)}), 401                
# Route Frontend Web Static
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
