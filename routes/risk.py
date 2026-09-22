"""KrishiMitra — Crop Risk Analysis route."""
from flask import Blueprint, render_template, request
from db.connection import fetch_all, fetch_one
from services.auth_service import login_required
from services import risk_engine

bp = Blueprint("risk", __name__)


@bp.route("/risk", methods=["GET", "POST"])
@login_required
def index():
    crops = fetch_all("SELECT CROP_ID, CROP_NAME FROM CROP WHERE IS_ACTIVE = 1 ORDER BY CROP_NAME")
    result = None
    selected_crop_id = None
    water_avail = request.values.get("water_availability", "MODERATE")

    crop_id = request.values.get("crop_id", type=int)
    if crop_id:
        selected_crop_id = crop_id
        crop = fetch_one("SELECT CROP_NAME FROM CROP WHERE CROP_ID = :cid", {"cid": crop_id})
        if crop:
            breakdown = risk_engine.get_risk_breakdown(crop_id, water_avail)
            result = {"crop_name": crop["crop_name"], **breakdown}

    return render_template(
        "risk.html", crops=crops, result=result,
        selected_crop_id=selected_crop_id, water_avail=water_avail,
    )
