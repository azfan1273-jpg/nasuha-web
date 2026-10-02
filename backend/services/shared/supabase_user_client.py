"""
Supabase client dengan JWT user (bukan anon/service key).

Kenapa perlu?
    - RLS pakai auth.uid() → harus ada JWT user di request.
    - Client global di supabase_config.py pakai anon key (role 'anon'),
      nggak punya auth.uid() → RLS nolak.
    - Setiap request yang butuh akses DB sebagai user, bikin client baru
      dengan JWT-nya di-inject ke PostgREST.

Catatan:
    - Bikin client baru per-request aman (thread-safe).
    - Jangan share client ke mutasi .postgrest.auth() lintas request —
      bakal race condition (FastAPI sync endpoint di threadpool).
"""

from supabase import create_client

from config.supabase_config import SUPABASE_URL, SUPABASE_KEY


def get_user_client(token: str):
    """
    Bikin Supabase client yang di-authenticate pakai JWT user.

    Args:
        token: JWT string (TANPA prefix "Bearer ").

    Returns:
        Supabase Client yang semua query-nya pakai auth.uid() = user_id.
    """
    if not token:
        raise ValueError("Token user kosong")

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Inject JWT user ke PostgREST → RLS lihat auth.uid()
    client.postgrest.auth(token)
    return client
