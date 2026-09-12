from flask import Blueprint, jsonify, request
from services.clay_service import get_clay_predictions
from config.supabase_config import supabase
import jwt

clay_bp = Blueprint('clay', __name__)

@clay_bp.route('/predict-tomorrow', methods=['GET'])
def predict_tomorrow():
    try:
        # 1. Cek Header Authorization
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token otentikasi tidak ditemukan'}), 401

        token = auth_header.split(' ')[1]

        # 2. Decode UID (sub) dari token JWT
        user_id = None
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get('sub') or payload.get('id')
        except Exception as jwt_err:
            return jsonify({'error': f'Gagal membaca token JWT: {str(jwt_err)}'}), 401

        if not user_id:
            return jsonify({'error': 'User ID tidak valid dalam token'}), 401

        # 3. Cari store_id dari tabel profiles KHUSUS milik UID ini
        store_id = request.args.get('store_id')

        if not store_id:
            try:
                prof_query = supabase.table('profiles').select('store_id').eq('id', user_id).execute()
                if prof_query.data and len(prof_query.data) > 0:
                    store_id = prof_query.data[0].get('store_id')
            except Exception as e:
                print(f"[CLAY DEBUG] Error fetch profile: {e}")

        # 4. Jika akun ini memang tidak punya store_id, TOLAK request-nya (Jangan bocorkan toko lain!)
        if not store_id:
            return jsonify({
                'status': 'error',
                'message': 'Akun Anda belum terhubung ke toko mana pun'
            }), 400

        # 5. Jalankan kalkulasi Clay Engine KHUSUS toko user ini
        clay_result = get_clay_predictions(store_id=store_id)
        raw_predictions = clay_result.get("predictions", []) if isinstance(clay_result, dict) else []

        return jsonify({
            'status': 'success',
            'store_id': store_id,
            'predictions': raw_predictions,
            'top_services': clay_result.get("top_services", []) if isinstance(clay_result, dict) else []
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
