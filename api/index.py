import os
import sys

# Ambil absolute path folder root project & folder backend
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(base_dir, 'backend')

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app

# Handler entrypoint Vercel
app = app
