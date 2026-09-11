import sys
import os

# Tambahkan folder backend ke path Python agar import routes & services tidak error
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app

# Export app sebagai handler utama Vercel
app = app
