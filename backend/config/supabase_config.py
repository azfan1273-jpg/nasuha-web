import os
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))
# Load file .env yang ada di folder root backend
load_dotenv(os.path.join(base_dir, '..', '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def get_supabase_headers(auth_header=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    if auth_header:
        headers["Authorization"] = auth_header
    return headers
