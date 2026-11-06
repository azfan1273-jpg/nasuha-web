"""Konfigurasi Predict Today."""

# Naikin dari 2 ke 3: Pelanggan baru wajib laundry 3x baru boleh diprediksi
MIN_TRANSACTIONS_FOR_PREDICTION = 3 
MIN_SERVICE_USAGE = 1

MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90

MAX_CARRY_OVER = 3

# Turunin dari 0.35 ke 0.20: Siklus harus lebih rapi. Kalau acak-acakan, buang!
MAX_RELATIVE_DEVIATION = 0.5 

# Kunci mati di 0: HANYA prediksi untuk HARI INI.
MATCH_DELTA_MIN = 0
MATCH_DELTA_MAX = 0