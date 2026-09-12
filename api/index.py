import sys
import os

# Tambahkan direktori backend ke sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from main import app
