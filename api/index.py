import sys
import os

# Tambahkan folder backend ke Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from main import app

# Export instance app untuk Serverless Function Vercel
app = app
