import os
import sys

# Absolute path ke folder root dan backend
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(base_dir, 'backend')

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app

# Set path folder static frontend agar kebaca Vercel
app.static_folder = os.path.join(base_dir, 'frontend')

app = app
