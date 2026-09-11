from flask import Flask, send_from_directory
from flask_cors import CORS
from routes.analytics import analytics_bp
from routes.clay_engine import clay_bp  # <-- TAMBAHAN 1

import os

# Set path folder frontend di luar folder backend
frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))

app = Flask(__name__, static_folder=frontend_folder, static_url_path='')
CORS(app) # Mengaktifkan CORS agar tidak diblokir browser

# Register Blueprint dari folder routes
app.register_blueprint(analytics_bp, url_prefix='/api')
app.register_blueprint(clay_bp, url_prefix='/api/clay')  # <-- TAMBAHAN 2

# Serve File Utama Frontend (index.html)
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# Serve Static Files (CSS, JS, Components)
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
