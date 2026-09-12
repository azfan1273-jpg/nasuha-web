from flask import Blueprint, jsonify, request
from services.clay_service import get_clay_predictions
from config.supabase_config import supabase

clay_bp = Blueprint('clay', __name__)

@clay_bp.route('/predict-tomorrow', methods=['GET'])
def predict_tomorrow():
    try:
        # 1. Ambil token dari Header Authorization
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Token otentikasi tidak ditemukan'}), 401
        
        token = auth_header.split(' ')[1]
        
        # 2. Verifikasi token ke Supabase Auth untuk mendapatkan data User
        try:
            user_response = supabase.auth.get_user(token)
            if not user_response or not user_response.user:
                return jsonify({'error': 'Sesi login tidak valid atau kadaluwarsa'}), 401
            user_id = user_response.user.id
        except Exception as auth_err:
            # Mengembalikan status 401 agar frontend tahu sesi perlu di-refresh
            return jsonify({'error': f'Auth Error: {str(auth_err)}'}), 401
        
        # 3. Ambil store_id milik user yang sedang login dari database
        # (Sesuaikan nama tabel profil/user kamu di Supabase, misal 'profiles' atau 'users')
        store_id = None
        try:
            # Ambil data profiles tanpa .single() agar tidak crash jika 0 rows
            store_query = supabase.table('profiles').select('store_id').eq('id', user_id).execute()
            if store_query.data and len(store_query.data) > 0:
                store_id = store_query.data[0].get('store_id')
        except Exception:
            pass

        # Fallback jika store_id kosong / tidak ada di tabel profiles
        if not store_id:
            store_id = user_id
        
        # 4. Jalankan prediksi khusus untuk store_id tersebut
        predictions = get_clay_predictions(store_id=store_id)
        
        return jsonify({
            'status': 'success',
            'store_id': store_id,
            'predictions': predictions
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
