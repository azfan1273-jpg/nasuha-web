import requests
from urllib.parse import quote
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, get_supabase_headers, verify_user_jwt
from security import is_rate_limited, sanitize_filter_value, is_valid_email

analytics_bp = Blueprint('analytics', __name__)


def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() if fwd else (request.remote_addr or 'unknown')


def _get_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer ') or len(auth_header) <= 7:
        return None
    return auth_header.split(' ', 1)[1].strip()


def _fetch_own_store_id(user_id, auth_header):
    """Ambil store_id milik user yang token-nya SUDAH terverifikasi."""
    uid = sanitize_filter_value(user_id)
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}&select=store_id",
        headers=get_supabase_headers(auth_header),
        timeout=10,
    )
    if res.status_code == 200 and res.json():
        return res.json()[0].get("store_id")
    return None


# 1. API Login — dengan rate limiting anti brute-force
@analytics_bp.route('/login', methods=['POST'])
def login():
    try:
        # Rate limit: maks 5 percobaan login per IP per menit
        if is_rate_limited(f"login:{_client_ip()}", limit=5, window=60):
            return jsonify({"status": "error", "message": "Terlalu banyak percobaan login. Coba lagi dalam 1 menit."}), 429

        data = request.get_json(silent=True) or {}
        email = str(data.get('email') or '').strip().lower()
        password = str(data.get('password') or '')

        if not email or not password:
            return jsonify({"status": "error", "message": "Email dan password wajib diisi"}), 400
        if not is_valid_email(email):
            return jsonify({"status": "error", "message": "Format email tidak valid"}), 400
        if len(password) > 128:
            return jsonify({"status": "error", "message": "Kredensial tidak valid"}), 401

        headers = {
            "apikey": get_supabase_headers()["apikey"],
            "Content-Type": "application/json",
        }
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
        payload = {"email": email, "password": password}

        res = requests.post(url, json=payload, headers=headers, timeout=15)

        if res.status_code != 200:
            # Jangan membocorkan detail internal Supabase; pesan generik saja.
            return jsonify({"status": "error", "message": "Email atau password salah"}), 401

        res_data = res.json()
        user_info = res_data.get("user", {})
        user_id = user_info.get("id")
        store_id = None

        # Ambil store_id milik user via token user yang baru didapat (RLS tetap berlaku)
        if user_id:
            try:
                user_auth_header = f"Bearer {res_data.get('access_token')}"
                store_id = _fetch_own_store_id(user_id, user_auth_header)
            except Exception:
                store_id = None

        return jsonify({
            "status": "success",
            "access_token": res_data.get("access_token"),
            "store_id": store_id,
            "user": user_info
        }), 200

    except requests.RequestException:
        return jsonify({"status": "error", "message": "Layanan sedang gangguan, coba lagi nanti"}), 503
    except Exception:
        # Jangan pernah mengembalikan str(e) ke client (information disclosure).
        return jsonify({"status": "error", "message": "Terjadi kesalahan pada server"}), 500


def _authorized_store_id(auth_header):
    """Verifikasi JWT user (signature+exp) lalu kembalikan store_id milik user tsb.

    Return (store_id, error_response). Ini memperbaiki IDOR: store_id TIDAK
    boleh lagi datang dari query parameter klien.
    """
    token = _get_bearer_token()
    if not token:
        return None, (jsonify({"status": "error", "message": "Sesi tidak valid, silakan login dulu"}), 401)
    try:
        payload = verify_user_jwt(token)
    except Exception:
        return None, (jsonify({"status": "error", "message": "Token tidak valid atau sudah kedaluwarsa, silakan login ulang"}), 401)

    user_id = payload.get('sub') or payload.get('id')
    if not user_id:
        return None, (jsonify({"status": "error", "message": "Token tidak memuat identitas user"}), 401)

    try:
        store_id = _fetch_own_store_id(user_id, auth_header)
    except requests.RequestException:
        return None, (jsonify({"status": "error", "message": "Layanan sedang gangguan, coba lagi nanti"}), 503)
    except Exception:
        return None, (jsonify({"status": "error", "message": "Terjadi kesalahan pada server"}), 500)

    if not store_id:
        return None, (jsonify({"status": "error", "message": "Akun Anda belum terhubung dengan toko mana pun"}), 400)
    return store_id, None


# 2. API Get Table Orders Database (STRICTLY filtered by store_id MILIK USER)
@analytics_bp.route('/transactions', methods=['GET'])
def get_transactions():
    try:
        auth_header = request.headers.get('Authorization')
        store_id, err = _authorized_store_id(auth_header)
        if err:
            return err

        sid = sanitize_filter_value(store_id)
        url = f"{SUPABASE_URL}/rest/v1/orders?select=*&store_id=eq.{quote(sid, safe='')}&order=id.desc&limit=500"
        res = requests.get(url, headers=get_supabase_headers(auth_header), timeout=15)

        if res.status_code != 200:
            return jsonify({"status": "error", "message": "Gagal mengambil data transaksi"}), 502

        return jsonify({"status": "success", "store_id": store_id, "data": res.json()}), 200

    except ValueError:
        return jsonify({"status": "error", "message": "Data toko tidak valid"}), 400
    except requests.RequestException:
        return jsonify({"status": "error", "message": "Layanan sedang gangguan, coba lagi nanti"}), 503
    except Exception:
        return jsonify({"status": "error", "message": "Terjadi kesalahan pada server"}), 500


# 3. API Get Downloads (hanya kolom publik, tanpa bocorkan baris tersembunyi)
@analytics_bp.route('/downloads', methods=['GET'])
def get_downloads():
    try:
        if is_rate_limited(f"downloads:{_client_ip()}", limit=30, window=60):
            return jsonify({"status": "error", "message": "Terlalu banyak permintaan"}), 429

        # Gunakan anon key + Authorization anon (bukan service key) agar RLS
        # di sisi Supabase tetap membatasi data yang boleh dibaca publik.
        anon_auth = f"Bearer {get_supabase_headers()['apikey']}"
        headers = get_supabase_headers(anon_auth)
        url = f"{SUPABASE_URL}/rest/v1/app_downloads?select=title,version,type,size,description,download_url,created_at&order=id.desc&limit=100"
        res = requests.get(url, headers=headers, timeout=15)

        if res.status_code != 200:
            return jsonify({"status": "error", "message": "Gagal mengambil data unduhan"}), 502

        return jsonify({"status": "success", "data": res.json()}), 200
    except requests.RequestException:
        return jsonify({"status": "error", "message": "Layanan sedang gangguan, coba lagi nanti"}), 503
    except Exception:
        return jsonify({"status": "error", "message": "Terjadi kesalahan pada server"}), 500
