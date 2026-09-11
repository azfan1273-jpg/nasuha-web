import sys
import os

# Dapatkan path root (nasuha-web) dan path backend
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, 'backend')

# Masukkan folder backend ke sys.path agar 'config' dan 'routes' langsung terbaca
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Import Flask app dari main.py di dalam folder backend
from main import app
