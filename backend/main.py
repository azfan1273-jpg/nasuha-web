import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config.supabase_config import supabase
from routes.analytics import analytics_bp
from routes.clay_engine import clay_bp

frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))

app = Flask(__name__, static_folder=frontend_folder, static_url_path='')
CORS(app)

# Register Blueprints
app.register_blueprint(analytics_bp, url_prefix='/api')
app.register_blueprint(clay_bp, url_prefix='/api/clay')

# Endpoint Login untuk Frontend Web
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Data JSON tidak ditemukan'}), 400
            
        email = data.get('email')
        password = data.get('password')

        # Cek apakah variabel supabase terinisialisasi
        if not supabase:
            return jsonify({'error': 'Supabase client gagal terkoneksi di Serverless Vercel'}), 500

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
            return jsonify({'error': 'Email atau password salah'}), 401

    except Exception as e:
        # Mengembalikan pesan error asli dalam format JSON
        return jsonify({'error': f'Backend Exception: {str(e)}'}), 500
        
# Route Frontend Web Static
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
