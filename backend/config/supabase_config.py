import os
from supabase import create_client, Client

url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

if not url or not key:
    # Jangan raise Exception agar app tidak mati total saat Vercel build, 
    # melainkan cetak warning untuk logging.
    print("WARNING: SUPABASE_URL atau SUPABASE_KEY belum terkonfigurasi di environment!")

supabase: Client = create_client(url, key)
