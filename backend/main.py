import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from config.supabase_config import supabase
from security import is_rate_limited, is_valid_email
from routes.analytics import analytics_bp
from routes.clay_engine import clay_bp

frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))

app = Flask(__name__, static_folder=frontend_folder, static_url_path='')

# CORS: BATASI origin. Di production, set ALLOWED_ORIGINS (comma-separated)
# di env Vercel, mis. "https://nasuha-web.vercel.app".
_dev = os.environ.get('FLASK_ENV', 'production').lower() == 'development'
_allowed_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', '').split(',') if o.strip()]
if _dev:
    CORS(app)  # hanya longgar saat development lokal
elif _allowed_origins:
    CORS(app, resources={r"/api/*": {"origins": _allowed_origins}})
else:
    # Production tanpa ALLOWED_ORIGINS: jangan izinkan cross-origin sama sekali.
    CORS(app, resources={r"/api/*": {"origins": []}})


# Headers keamanan global untuk semua response
@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    resp.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return resp


# Endpoint diagnostik ENV DIHAPUS — dulu membocorkan URL & prefix key Supabase.
# Jika butuh cek konfigurasi, gunakan log server, bukan endpoint publik.


# Register Blueprints
app.register_blueprint(analytics_bp, url_prefix='/api')
app.register_blueprint(clay_bp, url_prefix='/api/clay')


# Endpoint Login untuk Frontend Web
@app.route('/api/login', methods=['POST'])
def login():
    try:
        # Rate limiting anti brute-force: 5 percobaan / IP / menit
        fwd = request.headers.get('X-Forwarded-For', '')
        ip = fwd.split(',')[0].strip() if fwd else (request.remote_addr or 'unknown')
        if is_rate_limited(f"login:{ip}", limit=5, window=60):
            return jsonify({'error': 'Terlalu banyak percobaan login. Coba lagi dalam 1 menit.'}), 429

        data = request.get_json(silent=True) or {}
        email = str(data.get('email', '')).strip().lower()
        password = str(data.get('password', ''))

        if not email or not password:
            return jsonify({'error': 'Email dan password wajib diisi'}), 400
        if not is_valid_email(email) or len(password) > 128:
            return jsonify({'error': 'Kredensial tidak valid'}), 401

        if supabase is None:
            return jsonify({'error': 'Layanan sedang gangguan, coba lagi nanti'}), 503

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

    except Exception:
        # Pesan generik — JANGAN membocorkan detail exception/Supabase ke client,
        # dan JANGAN log alamat email user.
        print(f"[LOGIN ERROR] from {ip}: authentication failed")
        return jsonify({'error': 'Email atau password salah'}), 401


# Route Frontend Web Static (Handling Static & SPA Fallback)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    # Jika request mengarah ke API tapi tidak ketemu route-nya, kembalikan 404 JSON (jangan kirim HTML)
    if path.startswith('api/'):
        return jsonify({'error': 'Endpoint API tidak ditemukan'}), 404

    # Path traversal guard: pastikan target benar-benar di dalam folder frontend
    target_path = os.path.realpath(os.path.join(app.static_folder, path))
    static_root = os.path.realpath(app.static_folder)
    if not target_path.startswith(static_root + os.sep) and target_path != static_root:
        return jsonify({'error': 'Path tidak valid'}), 400

    # Cek apakah file fisik (css, js, png, dll) ada di folder frontend
    if path != "" and os.path.isfile(target_path):
        return send_from_directory(static_root, os.path.relpath(target_path, static_root))

    # Jika bukan file fisik atau route halaman web biasa, kirimkan index.html
    return send_from_directory(static_root, 'index.html')


if __name__ == '__main__':
    # debug=False default: debugger Werkzeug = RCE publik. Hanya aktifkan via env.
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='127.0.0.1', port=8080, debug=debug_mode)
