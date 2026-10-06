================================================================
PREDICTION v2.1 - Paket File Siap Timpa (nasuha-web)
================================================================

ISI PAKET (path relatif terhadap root repo lo):

  FILE BARU (modul prediksi v2.1):
    backend/services/prediction/__init__.py
    backend/services/prediction/cycle.py
    backend/services/prediction/evaluator.py
    backend/services/prediction/predictor.py
    backend/services/prediction/segmentation.py
    backend/services/prediction/weights.py
    backend/tests/test_prediction_v2_offline.py

  FILE DEPENDENSI shared/ (Bawaan - cek dulu!):
    backend/services/shared/__init__.py
    backend/services/shared/customer_utils.py
    backend/services/shared/datetime_utils.py
    backend/services/shared/order_utils.py
    backend/services/shared/supabase_user_client.py
  -> Kalau file-file shared/ ini SUDAH ADA di repo lokal lo,
     JANGAN ditimpa (skip). Mereka cuma dibundel biar tes bisa
     jalan di folder kosong. Kalau mau aman, extract ke folder
     sementara dulu lalu salin manual hanya prediction/ & tests/.

CARA PAKAI:
  1. Extract zip ini ke folder NASUHA-WEB lo.
  2. Modul v2.1 terpisah - TIDAK menimpa kode produksi lama.
     Orchestrator produksi masih pakai modul lama, jadi aman.
  3. Jalanin test offline buat verifikasi:
       python backend/tests/test_prediction_v2_offline.py
     Target output: "SEMUA ASSERT LULUS" dengan
     accuracy(+-1d toleransi) >= 60%.
  4. Commit & push:
       git add backend/services/prediction backend/tests/test_prediction_v2_offline.py
       git commit -m "feat(prediction-v2.1): EWM cycle, feedback loop, kalender, segmentasi"
       git push

CATATAN:
  - Modul ini BELUM di-wire ke route /api/clay produksi.
    Untuk mengaktifkan, perlu switch orchestrator (opsi A).
  - Perubahan #5 (stabilisasi input data / Supabase index &
    constraint) sengaja BELUM dikerjakan - menunggu diskusi.
================================================================
