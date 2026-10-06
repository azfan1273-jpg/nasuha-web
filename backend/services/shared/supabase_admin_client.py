"""Supabase client dengan service_role key (bypass RLS).

HANYA untuk operasi server-side tanpa JWT user (misal: cron).
JANGAN dipakai di code yang expose ke frontend.
"""

import logging
import os

from supabase import create_client

from config.supabase_config import SUPABASE_URL

logger = logging.getLogger(__name__)


def get_admin_auth_header():
    """Return 'Bearer <service_role_key>' atau raise kalau kosong."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tidak diset")
    return f"Bearer {key}"


def get_admin_client():
    """Supabase client dengan service role (bypass RLS)."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tidak diset")
    return create_client(SUPABASE_URL, key)
