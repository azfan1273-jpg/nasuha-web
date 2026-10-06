"""Prediction service — target kedatangan harian + evaluasi akurasi.

Import eksplisit ditunda (lazy) supaya modul murni-siklus seperti
`cycle.py` bisa dipakai/dites tanpa dependency Supabase.
"""


def __getattr__(name):
    if name == "predict_arrivals":
        from services.prediction.predictor import predict_arrivals
        return predict_arrivals
    if name == "evaluate_prediction_logs":
        from services.prediction.evaluator import evaluate_prediction_logs
        return evaluate_prediction_logs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
