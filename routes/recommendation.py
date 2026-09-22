"""
KrishiMitra — Smart Crop Recommendation & What-If Simulator routes.
"""
from flask import Blueprint, render_template, request, session, abort, jsonify
from db.connection import fetch_all, fetch_one
from services.auth_service import login_required
from services import recommendation_engine as engine

bp = Blueprint("recommendation", __name__)


def _farmer_farms():
    return fetch_all(
        "SELECT FARM_ID, FARM_NAME FROM FARM WHERE FARMER_ID = :fid ORDER BY CREATED_AT DESC",
        {"fid": session["farmer_id"]},
    )


def _farm_or_403(farm_id):
    farm = fetch_one(
        """
        SELECT fm.*, s.SOIL_NAME FROM FARM fm JOIN SOIL s ON s.SOIL_ID = fm.SOIL_ID
        WHERE fm.FARM_ID = :fid AND fm.FARMER_ID = :farmer_id
        """,
        {"fid": farm_id, "farmer_id": session["farmer_id"]},
    )
    if not farm:
        abort(403)
    return farm


def _last_crop_id(farm_id):
    row = fetch_one(
        """
        SELECT CROP_ID FROM (
            SELECT CROP_ID FROM CROP_HISTORY WHERE FARM_ID = :fid ORDER BY PLANTING_DATE DESC
        ) WHERE ROWNUM = 1
        """,
        {"fid": farm_id},
    )
    return row["crop_id"] if row else None


@bp.route("/recommendation")
@login_required
def index():
    farms = _farmer_farms()
    farm_id = request.args.get("farm_id", type=int)
    selected_farm = None
    results = None
    budget = request.args.get("budget", type=float)

    if farms and (farm_id or len(farms) == 1):
        farm_id = farm_id or farms[0]["farm_id"]
        selected_farm = _farm_or_403(farm_id)
        last_crop_id = _last_crop_id(farm_id)
        results = engine.generate_recommendations(
            soil_id=selected_farm["soil_id"],
            season_id=selected_farm["current_season_id"],
            water_avail=selected_farm["water_availability"],
            budget=budget,
            land_area=float(selected_farm["land_area_acres"]),
            last_crop_id=last_crop_id,
        )
        engine.persist_recommendations(farm_id, results, scenario_tag="CURRENT")

    return render_template(
        "recommendation.html", farms=farms, selected_farm=selected_farm,
        results=results, budget=budget,
    )


@bp.route("/simulator")
@login_required
def simulator():
    farms = _farmer_farms()
    farm_id = request.args.get("farm_id", type=int)
    selected_farm = None

    if farms:
        farm_id = farm_id or farms[0]["farm_id"]
        selected_farm = _farm_or_403(farm_id)

    soils = fetch_all("SELECT SOIL_ID, SOIL_NAME FROM SOIL ORDER BY SOIL_NAME")
    seasons = fetch_all("SELECT SEASON_ID, SEASON_NAME FROM SEASON ORDER BY SEASON_ID")

    return render_template(
        "simulator.html", farms=farms, selected_farm=selected_farm, soils=soils, seasons=seasons,
    )


@bp.route("/simulator/run", methods=["POST"])
@login_required
def simulator_run():
    """AJAX endpoint: re-run the engine for an arbitrary hypothetical
    scenario and return ranked JSON results, without persisting anything
    to RECOMMENDATION unless the farmer explicitly saves a scenario."""
    data = request.get_json(force=True, silent=True) or {}

    farm_id = data.get("farm_id")
    if farm_id:
        farm = _farm_or_403(int(farm_id))
        last_crop_id = _last_crop_id(int(farm_id))
    else:
        farm = None
        last_crop_id = None

    try:
        soil_id = int(data.get("soil_id"))
        season_id = int(data.get("season_id"))
        water_avail = data.get("water_availability")
        land_area = float(data.get("land_area"))
        budget = float(data["budget"]) if data.get("budget") not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid scenario inputs."}), 400

    results = engine.generate_recommendations(
        soil_id=soil_id, season_id=season_id, water_avail=water_avail,
        budget=budget, land_area=land_area, last_crop_id=last_crop_id,
    )

    if farm_id and data.get("save_scenario"):
        engine.persist_recommendations(int(farm_id), results, scenario_tag="WHAT_IF")

    return jsonify({"results": results})
