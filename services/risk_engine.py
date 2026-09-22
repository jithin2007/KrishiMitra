"""
KrishiMitra — Crop Risk Analysis engine.

Reads per-risk-type scores (0-100) from CROP_RISK and combines them
into a single "Krishi Risk Score" using weights that shift slightly
based on the farm's own water availability (a farm with LOW water
availability is more exposed to a crop's water risk, so that
component is weighted higher).
"""
from db.connection import fetch_all

RISK_TYPES = ["WATER", "SOIL", "DISEASE", "MARKET", "WEATHER"]

_BASE_WEIGHTS = {"WATER": 0.25, "SOIL": 0.15, "DISEASE": 0.20, "MARKET": 0.20, "WEATHER": 0.20}

_ADVICE = {
    "WATER": "Consider choosing a crop with lower water requirements, or improve irrigation reliability (e.g. drip irrigation).",
    "SOIL": "A soil test and targeted amendments can reduce soil-related risk for this crop.",
    "DISEASE": "Plan for preventive pest/disease management and consider disease-resistant seed varieties.",
    "MARKET": "Track mandi prices and consider forward contracts or staggered selling to reduce market risk.",
    "WEATHER": "Keep an eye on the seasonal forecast; consider crop insurance for weather-sensitive crops.",
}


def get_risk_breakdown(crop_id, water_avail=None):
    rows = fetch_all(
        "SELECT RISK_TYPE, RISK_SCORE, NOTES FROM CROP_RISK WHERE CROP_ID = :cid",
        {"cid": crop_id},
    )
    scores = {r["risk_type"]: float(r["risk_score"]) for r in rows}
    notes = {r["risk_type"]: r["notes"] for r in rows}

    weights = dict(_BASE_WEIGHTS)
    if water_avail == "LOW":
        weights["WATER"] = 0.35
    elif water_avail == "HIGH":
        weights["WATER"] = 0.15
    # renormalise so weights sum to 1 (extra/deficit absorbed by WEATHER)
    fixed_sum = weights["SOIL"] + weights["DISEASE"] + weights["MARKET"]
    weights["WEATHER"] = 1 - weights["WATER"] - fixed_sum

    overall = sum(scores.get(t, 0) * weights[t] for t in RISK_TYPES)
    overall = round(overall, 1)

    if overall < 35:
        label = "LOW RISK"
    elif overall < 60:
        label = "MEDIUM RISK"
    else:
        label = "HIGH RISK"

    # Advise on whichever risk factor is currently highest
    if scores:
        top_risk_type = max(scores, key=scores.get)
        advice = _ADVICE.get(top_risk_type, "")
    else:
        top_risk_type, advice = None, ""

    return {
        "overall_score": overall,
        "label": label,
        "by_type": {t: scores.get(t, 0) for t in RISK_TYPES},
        "notes": notes,
        "weights_used": weights,
        "top_risk_type": top_risk_type,
        "advice": advice,
    }
