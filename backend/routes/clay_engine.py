import requests
from urllib.parse import quote
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, get_supabase_headers, verify_user_jwt
from services.clay_service import calculate_tomorrow_prediction
from security import is_rate_limited, sanitize_filter_value

clay_bp = Blueprint('clay', __name__)


@clay_bp.route('/predict-tomorrow', methods=['GET'])
def predict_tomorrow():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'status': 'error', 'message': 'Token otentikasi tidak ditemukan'}), 401

        token = auth_header.split(' ', 1)[1].strip()

        # Rate limit per user (sub JWT jika bisa didekode, fallback IP)
        rate_key = f"clay:{request.remote_addr}"
        if is_rate_limited(rate_key, limit=20, window=60):
            return jsonify({'status': 'error', 'message': 'Terlalu banyak permintaan'}), 429

        # 1. VERIFIKASI TOKEN (signature + expiry) — bukan decode tanpa verifikasi.
        try:
            payload = verify_user_jwt(token)
        except Exception:
            return jsonify({'status': 'error', 'message': 'Token tidak valid atau kedaluwarsa, silakan login ulang'}), 401

        user_id = payload.get('sub') or payload.get('id')
        if not user_id:
            return jsonify({'status': 'error', 'message': 'Token tidak memuat identitas user'}), 401

        # 2. store_id SELALU diambil dari profil user yang terverifikasi.
        #    Query parameter ?store_id dari klien DIABAIKAN (menutup IDOR).
        uid = sanitize_filter_value(user_id)
        prof_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{quote(uid, safe='')}&select=store_id",
            headers=get_supabase_headers(auth_header),
            timeout=15,
        )
        store_id = None
        if prof_res.status_code == 200 and len(prof_res.json()) > 0:
            store_id = prof_res.json()[0].get('store_id')

        if not store_id:
            return jsonify({
                'status': 'error',
                'message': 'Gagal mengidentifikasi store_id toko. Silakan login ulang.'
            }), 400

        sid = sanitize_filter_value(store_id)

        # 3. Ambil data orders + order_items KHUSUS store_id milik user ini.
        orders_url = f"{SUPABASE_URL}/rest/v1/orders?select=*,order_items(*)&store_id=eq.{quote(sid, safe='')}&limit=2000"
        orders_res = requests.get(orders_url, headers=get_supabase_headers(auth_header), timeout=30)

        if orders_res.status_code != 200:
            return jsonify({'status': 'error', 'message': 'Gagal mengambil data orders'}), 502

        orders_data = orders_res.json() or []

        # 4. Jalankan kalkulasi Clay Engine Python
        clay_result = calculate_tomorrow_prediction(orders_data)
        raw_predictions = clay_result.get("predictions", []) if isinstance(clay_result, dict) else []

        return jsonify({
            'status': 'success',
            'store_id': store_id,
            'predictions': raw_predictions,
            'top_services': clay_result.get("top_services", []) if isinstance(clay_result, dict) else []
        }), 200

    except ValueError:
        return jsonify({'status': 'error', 'message': 'Data tidak valid'}), 400
    except requests.RequestException:
        return jsonify({'status': 'error', 'message': 'Layanan sedang gangguan, coba lagi nanti'}), 503
    except Exception:
        return jsonify({'status': 'error', 'message': 'Terjadi kesalahan pada server'}), 500
