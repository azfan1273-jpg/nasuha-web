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

        # Memanggil Auth Supabase
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        # Ekstrak data user & session
        user_data = response.user.dict() if hasattr(response.user, 'dict') else response.user
        session_data = response.session.dict() if hasattr(response.session, 'dict') else response.session
        token = response.session.access_token if response.session else None

        return jsonify({
            'message': 'Login berhasil',
            'user': user_data,
            'session': session_data,
            'access_token': token
        }), 200

    except Exception as e:
        # Ambil detail pesan error asli dari Exception Supabase
        error_detail = str(e)
        if hasattr(e, 'message'):
            error_detail = e.message
        elif hasattr(e, 'args') and len(e.args) > 0:
            error_detail = str(e.args[0])

        print(f"[LOGIN ERROR] Email: {email} | Exception: {error_detail}")
        return jsonify({'error': f"Supabase Auth Error: {error_detail}"}), 401                

# Route Frontend Web Static (Handling Static & SPA Fallback)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    # Jika request mengarah ke API tapi tidak ketemu route-nya, kembalikan 404 JSON (jangan kirim HTML)
    if path.startswith('api/'):
        return jsonify({'error': 'Endpoint API tidak ditemukan'}), 404

    # Cek apakah file fisik (css, js, png, dll) ada di folder frontend
    target_path = os.path.join(app.static_folder, path)
    if path != "" and os.path.exists(target_path) and os.path.isfile(target_path):
        return send_from_directory(app.static_folder, path)
    else:
        # Jika bukan file fisik atau route halaman web biasa, kirimkan index.html
        return send_from_directory(app.static_folder, 'index.html')
        
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
