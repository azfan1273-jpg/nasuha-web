import os
import sys

# Absolute path ke folder root dan backend
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(base_dir, 'backend')

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app  # noqa: E402

# Path folder static frontend (dipakai main.py)
app_frontend = os.path.join(base_dir, 'frontend')
app.state.frontend_folder = app_frontend  # opsional, buat debugging

# Vercel: cari objek `app` (ASGI) atau `handler`.
# Kalau runtime butuh AWS Lambda-style handler, Mangum jadi jembatan.
try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except ImportError:
    handler = app
