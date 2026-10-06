"""Skoring confidence prediksi."""


def calculate_score(delta, deviation, median_cycle, tx_count):
    timing = 100 if delta == 0 else 90

    if median_cycle <= 0:
        consistency = 0.7
    else:
        rel = deviation / median_cycle
        if rel <= 0.15:   consistency = 1.0
        elif rel <= 0.30: consistency = 0.9
        elif rel <= 0.50: consistency = 0.75
        else:             consistency = 0.6

    if tx_count >= 10:   history = 1.0
    elif tx_count >= 7:  history = 0.95
    elif tx_count >= 5:  history = 0.9
    elif tx_count >= 4:  history = 0.85
    else:                history = 0.8

    return max(0, min(100, round(timing * consistency * history)))


def get_confidence_level(score):
    if score >= 80: return "high"
    if score >= 60: return "medium"
    return "low"
