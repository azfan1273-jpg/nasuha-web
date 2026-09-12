import requests
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, get_supabase_headers

analytics_bp = Blueprint('analytics', __name__)

# 1. API Get Login Akun by store
@analytics_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"status": "error", "message": "Email dan password wajib diisi"}), 400

        headers = get_supabase_headers()
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
        payload = {
            "email": email,
            "password": password
        }

        res = requests.post(url, json=payload, headers=headers)
        res_data = res.json()

        if res.status_code != 200:
            return jsonify({"status": "error", "message": res_data.get("error_description", "Login gagal")}), res.status_code

        # --- AMBIL STORE_ID MILIK USER ---
        user_info = res_data.get("user", {})
        user_id = user_info.get("id")
        store_id = None

        if user_id:
            try:
                # 1. Cek ke tabel profiles
                prof_res = requests.get(
                    f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=store_id",
                    headers=headers
                )
                if prof_res.status_code == 200 and len(prof_res.json()) > 0:
                    store_id = prof_res.json()[0].get("store_id")
            except Exception:
                pass

        # 2. Fallback jika profiles kosong, ambil ID toko dari tabel stores
        if not store_id:
            try:
                store_res = requests.get(
                    f"{SUPABASE_URL}/rest/v1/stores?select=id&limit=1",
                    headers=headers
                )
                if store_res.status_code == 200 and len(store_res.json()) > 0:
                    store_id = store_res.json()[0].get("id")
            except Exception:
                pass

        return jsonify({
            "status": "success",
            "access_token": res_data.get("access_token"),
            "store_id": store_id,
            "user": user_info
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 2. API Get Table Orders Database
@analytics_bp.route('/transactions', methods=['GET'])
def get_transactions():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"status": "error", "message": "Sesi tidak valid, silakan login dulu"}), 401

        # Meneruskan token JWT user ke Supabase via supabase_config
        user_headers = get_supabase_headers(auth_header)

        url = f"{SUPABASE_URL}/rest/v1/orders?select=*"
        res = requests.get(url, headers=user_headers)
        
        if res.status_code != 200:
            return jsonify({"status": "error", "message": res.text}), res.status_code

        return jsonify({"status": "success", "data": res.json()}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 3. API Get Downloads
@analytics_bp.route('/downloads', methods=['GET'])
def get_downloads():
    try:
        headers = get_supabase_headers()
        url = f"{SUPABASE_URL}/rest/v1/app_downloads?select=*&order=id.desc"
        res = requests.get(url, headers=headers)
        
        if res.status_code != 200:
            return jsonify({"status": "error", "message": res.text}), res.status_code
            
        return jsonify({"status": "success", "data": res.json()}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

