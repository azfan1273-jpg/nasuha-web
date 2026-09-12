import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error init Supabase: {e}")

# Fungsi helper header (opsional menerima token JWT user)
def get_supabase_headers(auth_header=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    if auth_header:
        headers["Authorization"] = auth_header
    else:
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return headers
