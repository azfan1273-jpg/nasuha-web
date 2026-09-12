import sys
import os

# Tambahkan path folder backend ke sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from main import app

# Handler entrypoint untuk Vercel Serverless Function
app = app
