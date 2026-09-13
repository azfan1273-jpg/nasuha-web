import requests
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, get_supabase_headers
import jwt

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
        payload = {"email": email, "password": password}

        res = requests.post(url, json=payload, headers=headers)
        res_data = res.json()

        if res.status_code != 200:
            return jsonify({"status": "error", "message": res_data.get("error_description", "Login gagal")}), res.status_code

        user_info = res_data.get("user", {})
        user_id = user_info.get("id")
        store_id = None

        # AMBIL STORE_ID DARI TABEL PROFILES BERDASARKAN UID (PERSIS SEPERTI FLUTTER)
        if user_id:
            try:
                prof_res = requests.get(
                    f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=store_id",
                    headers=headers
                )
                if prof_res.status_code == 200 and len(prof_res.json()) > 0:
                    store_id = prof_res.json()[0].get("store_id")
            except Exception as e:
                print(f"Error fetch profile store_id: {e}")

        return jsonify({
            "status": "success",
            "access_token": res_data.get("access_token"),
            "store_id": store_id,
            "user": user_info
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 2. API Get Table Orders Database (STRICTLY FILTERED BY STORE_ID)
@analytics_bp.route('/transactions', methods=['GET'])
def get_transactions():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"status": "error", "message": "Sesi tidak valid, silakan login dulu"}), 401

        token = auth_header.split(' ')[1]
        user_headers = get_supabase_headers(auth_header)

        # 1. Cek store_id dari query parameter (?store_id=xxx)
        store_id = request.args.get('store_id')

        # 2. Jika tidak ada, fetch store_id dari profiles via JWT Token
        if not store_id or store_id in ['null', 'undefined', 'None', '']:
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = payload.get('sub') or payload.get('id')
                
                if user_id:
                    prof_res = requests.get(
                        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=store_id",
                        headers=user_headers
                    )
                    if prof_res.status_code == 200 and len(prof_res.json()) > 0:
                        store_id = prof_res.json()[0].get("store_id")
            except Exception as err:
                print(f"[TRANSACTIONS DEBUG] Error decoding JWT or fetching profile: {err}")

        # 3. Jika store_id tetap tidak ada, batasi agar tidak membocorkan data toko lain
        if not store_id or store_id in ['null', 'undefined', 'None', '']:
            return jsonify({"status": "error", "message": "Akun Anda belum terhubung dengan toko mana pun"}), 400

        # 4. Query orders strictly filtered by store_id
        url = f"{SUPABASE_URL}/rest/v1/orders?select=*&store_id=eq.{store_id}&order=id.desc"
        res = requests.get(url, headers=user_headers)
        
        if res.status_code != 200:
            return jsonify({"status": "error", "message": res.text}), res.status_code

        return jsonify({"status": "success", "store_id": store_id, "data": res.json()}), 200

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
