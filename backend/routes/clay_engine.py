from flask import Blueprint, jsonify, request
from services.clay_service import get_clay_predictions
from config.supabase_config import supabase
import jwt

clay_bp = Blueprint('clay', __name__)

@clay_bp.route('/predict-tomorrow', methods=['GET'])
def predict_tomorrow():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token otentikasi tidak ditemukan'}), 401

        token = auth_header.split(' ')[1]

        # Decode UID dari JWT Token
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get('sub')
        except Exception as jwt_err:
            return jsonify({'error': f'Gagal membaca token: {str(jwt_err)}'}), 401

        # Cek store_id dari Query Parameter atau cari ke tabel profiles via UID
        store_id = request.args.get('store_id')

        if not store_id and user_id:
            try:
                prof_query = supabase.table('profiles').select('store_id').eq('id', user_id).execute()
                if prof_query.data and len(prof_query.data) > 0:
                    store_id = prof_query.data[0].get('store_id')
            except Exception as e:
                print(f"Error fetching profile: {e}")

        if not store_id:
            return jsonify({'error': 'store_id tidak ditemukan untuk akun ini di tabel profiles'}), 404

        # Jalankan kalkulasi Clay Engine berdasarkan store_id toko Nasuha
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
