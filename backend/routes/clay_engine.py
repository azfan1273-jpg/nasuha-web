import requests
from flask import Blueprint, jsonify, request
from config.supabase_config import SUPABASE_URL, get_supabase_headers
from services.clay_service import calculate_tomorrow_prediction

clay_bp = Blueprint('clay', __name__)

@clay_bp.route('/predict-tomorrow', methods=['GET'])
def get_tomorrow_prediction():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        headers = get_supabase_headers(auth_header)

        # Tarik data orders lengkap dengan join ke order_items(service_name)
        url = f"{SUPABASE_URL}/rest/v1/orders?select=id,customer_name,customer_phone,total_price,created_at,order_items(service_name)"
        res = requests.get(url, headers=headers)

        if res.status_code != 200:
            return jsonify({"status": "error", "message": res.text}), res.status_code

        orders = res.json()
        prediction_result = calculate_tomorrow_prediction(orders)

        return jsonify(prediction_result), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
