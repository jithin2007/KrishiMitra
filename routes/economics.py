"""KrishiMitra — Farming Economics calculator route."""
from flask import Blueprint, render_template, request
from db.connection import fetch_all
from services.auth_service import login_required
from services import economics as econ_service

bp = Blueprint("economics", __name__)


@bp.route("/economics", methods=["GET", "POST"])
@login_required
def index():
    crops = fetch_all("SELECT CROP_ID, CROP_NAME FROM CROP WHERE IS_ACTIVE = 1 ORDER BY CROP_NAME")
    result = None
    form = {}

    if request.method == "POST":
        form = request.form
        try:
            crop_id = int(form.get("crop_id"))
            land_area = float(form.get("land_area") or 1)

            def _opt(name):
                val = form.get(name)
                return float(val) if val not in (None, "") else None

            result = econ_service.calculate_economics(
                crop_id=crop_id, land_area=land_area,
                seed_cost=_opt("seed_cost"), fertilizer_cost=_opt("fertilizer_cost"),
                labour_cost=_opt("labour_cost"), irrigation_cost=_opt("irrigation_cost"),
                other_cost=_opt("other_cost"),
            )
        except (TypeError, ValueError) as exc:
            result = {"error": "Please check your inputs and try again."}

    return render_template("economics.html", crops=crops, result=result, form=form)
