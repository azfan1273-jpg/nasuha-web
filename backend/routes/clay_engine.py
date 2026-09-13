import requests
import jwt
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, SUPABASE_KEY, get_supabase_headers
from services.clay_service import calculate_tomorrow_prediction

clay_bp = Blueprint('clay', __name__)

@clay_bp.route('/predict-tomorrow', methods=['GET'])
def predict_tomorrow():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'status': 'error', 'message': 'Token otentikasi tidak ditemukan'}), 401

        token = auth_header.split(' ')[1]
        user_headers = get_supabase_headers(auth_header)

        # 1. Ambil store_id dari Query String (jika dikirim frontend)
        store_id = request.args.get('store_id')

        # 2. Jika store_id kosong, fetch via REST API dari profiles
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
                        store_id = prof_res.json()[0].get('store_id')
            except Exception as err:
                print(f"[CLAY DEBUG] JWT decode / profile error: {err}")

        # 3. Validasi store_id
        if not store_id or store_id in ['null', 'undefined', 'None', '']:
            return jsonify({
                'status': 'error',
                'message': 'Gagal mengidentifikasi store_id toko. Silakan login ulang.'
            }), 400

        # 4. Ambil data orders + order_items KHUSUS store_id ini via REST API
        orders_url = f"{SUPABASE_URL}/rest/v1/orders?select=*,order_items(*)&store_id=eq.{store_id}"
        orders_res = requests.get(orders_url, headers=user_headers)

        if orders_res.status_code != 200:
            return jsonify({'status': 'error', 'message': f'Gagal mengambil data orders: {orders_res.text}'}), orders_res.status_code

        orders_data = orders_res.json() or []

        # 5. Jalankan kalkulasi Clay Engine Python
        clay_result = calculate_tomorrow_prediction(orders_data)
        raw_predictions = clay_result.get("predictions", []) if isinstance(clay_result, dict) else []

        return jsonify({
            'status': 'success',
            'store_id': store_id,
            'predictions': raw_predictions,
            'top_services': clay_result.get("top_services", []) if isinstance(clay_result, dict) else []
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
