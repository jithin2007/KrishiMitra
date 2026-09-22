"""
KrishiMitra — farmer-facing routes: dashboard, farm management, crop
history, and profile. Every query is scoped to session['farmer_id'] so
a farmer can never read or modify another farmer's records.
"""
import logging
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort
import oracledb

from db.connection import fetch_all, fetch_one, execute_dml, call_procedure, get_connection
from services.auth_service import login_required

bp = Blueprint("farmer", __name__)
logger = logging.getLogger("krishimitra.farmer")


def _lookups():
    soils = fetch_all("SELECT SOIL_ID, SOIL_NAME FROM SOIL ORDER BY SOIL_NAME")
    seasons = fetch_all("SELECT SEASON_ID, SEASON_NAME FROM SEASON ORDER BY SEASON_ID")
    return soils, seasons


def _owns_farm(farm_id, farmer_id):
    row = fetch_one("SELECT FARM_ID FROM FARM WHERE FARM_ID=:fid AND FARMER_ID=:farmer_id",
                     {"fid": farm_id, "farmer_id": farmer_id})
    return row is not None


# --------------------------- DASHBOARD -------------------------------

@bp.route("/dashboard")
@login_required
def dashboard():
    farmer_id = session["farmer_id"]

    summary = fetch_one("SELECT * FROM FARMER_FARM_SUMMARY WHERE FARMER_ID = :fid", {"fid": farmer_id}) or {
        "total_farms": 0, "total_land_acres": 0, "active_crops": 0, "total_profit": 0
    }

    farms = fetch_all("SELECT FARM_ID, FARM_NAME FROM FARM WHERE FARMER_ID = :fid ORDER BY CREATED_AT DESC",
                       {"fid": farmer_id})

    top_recommendation = None
    if farms:
        top_recommendation = fetch_one(
            """
            SELECT r.CROP_ID, c.CROP_NAME, r.SUITABILITY_SCORE, r.RISK_LABEL
            FROM RECOMMENDATION r JOIN CROP c ON c.CROP_ID = r.CROP_ID
            WHERE r.FARM_ID = :fid AND r.SCENARIO_TAG = 'CURRENT'
            ORDER BY r.SUITABILITY_SCORE DESC FETCH FIRST 1 ROWS ONLY
            """,
            {"fid": farms[0]["farm_id"]},
        )

    recent_history = fetch_all(
        """
        SELECT ch.HISTORY_ID, c.CROP_NAME, f.FARM_NAME, ch.PLANTING_DATE, ch.HARVEST_DATE, ch.PROFIT
        FROM CROP_HISTORY ch
        JOIN FARM f ON f.FARM_ID = ch.FARM_ID
        JOIN CROP c ON c.CROP_ID = ch.CROP_ID
        WHERE f.FARMER_ID = :fid
        ORDER BY ch.PLANTING_DATE DESC FETCH FIRST 5 ROWS ONLY
        """,
        {"fid": farmer_id},
    )

    profit_trend = fetch_all(
        """
        SELECT c.CROP_NAME, ch.PROFIT, ch.PLANTING_DATE
        FROM CROP_HISTORY ch JOIN FARM f ON f.FARM_ID = ch.FARM_ID JOIN CROP c ON c.CROP_ID = ch.CROP_ID
        WHERE f.FARMER_ID = :fid AND ch.PROFIT IS NOT NULL
        ORDER BY ch.PLANTING_DATE ASC
        """,
        {"fid": farmer_id},
    )

    crop_distribution = fetch_all(
        """
        SELECT c.CROP_NAME, COUNT(*) AS cnt
        FROM CROP_HISTORY ch JOIN FARM f ON f.FARM_ID = ch.FARM_ID JOIN CROP c ON c.CROP_ID = ch.CROP_ID
        WHERE f.FARMER_ID = :fid
        GROUP BY c.CROP_NAME
        """,
        {"fid": farmer_id},
    )

    return render_template(
        "dashboard.html",
        summary=summary, farms=farms, top_recommendation=top_recommendation,
        recent_history=recent_history, profit_trend=profit_trend, crop_distribution=crop_distribution,
    )


# --------------------------- FARM CRUD -------------------------------

@bp.route("/farms")
@login_required
def farms():
    farmer_id = session["farmer_id"]
    rows = fetch_all(
        """
        SELECT fm.FARM_ID, fm.FARM_NAME, fm.LOCATION, fm.LAND_AREA_ACRES, s.SOIL_NAME,
               fm.IRRIGATION_TYPE, fm.WATER_AVAILABILITY, se.SEASON_NAME
        FROM FARM fm
        JOIN SOIL s ON s.SOIL_ID = fm.SOIL_ID
        LEFT JOIN SEASON se ON se.SEASON_ID = fm.CURRENT_SEASON_ID
        WHERE fm.FARMER_ID = :fid
        ORDER BY fm.CREATED_AT DESC
        """,
        {"fid": farmer_id},
    )
    return render_template("farms.html", farms=rows)


@bp.route("/farms/add", methods=["GET", "POST"])
@login_required
def add_farm():
    soils, seasons = _lookups()

    if request.method == "GET":
        return render_template("add_farm.html", soils=soils, seasons=seasons)

    farmer_id = session["farmer_id"]
    form = request.form
    errors = []

    farm_name = (form.get("farm_name") or "").strip()
    location = (form.get("location") or "").strip()
    try:
        land_area = float(form.get("land_area") or 0)
    except ValueError:
        land_area = 0
    soil_id = form.get("soil_id")
    irrigation_type = form.get("irrigation_type")
    water_availability = form.get("water_availability")
    season_id = form.get("season_id") or None
    notes = (form.get("notes") or "").strip() or None

    if not farm_name or len(farm_name) < 2:
        errors.append("Please enter a farm name.")
    if not location:
        errors.append("Please enter a location.")
    if land_area <= 0:
        errors.append("Land area must be greater than zero.")
    if not soil_id:
        errors.append("Please select a soil type.")
    if irrigation_type not in ("RAINFED", "BOREWELL", "CANAL", "DRIP", "SPRINKLER"):
        errors.append("Please select a valid irrigation type.")
    if water_availability not in ("LOW", "MODERATE", "HIGH"):
        errors.append("Please select water availability.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("add_farm.html", soils=soils, seasons=seasons, form=form)

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            out_farm_id = cur.var(int)
            cur.callproc(
                "ADD_FARM",
                [farmer_id, farm_name, location, land_area, int(soil_id), irrigation_type,
                 water_availability, int(season_id) if season_id else None, notes, out_farm_id],
            )
        conn.commit()
    except oracledb.DatabaseError:
        logger.exception("Failed to add farm")
        flash("Could not save the farm. Please try again.", "danger")
        return render_template("add_farm.html", soils=soils, seasons=seasons, form=form)

    flash(f'Farm "{farm_name}" added successfully.', "success")
    return redirect(url_for("farmer.farms"))


@bp.route("/farms/<int:farm_id>/edit", methods=["GET", "POST"])
@login_required
def edit_farm(farm_id):
    farmer_id = session["farmer_id"]
    if not _owns_farm(farm_id, farmer_id):
        abort(403)

    soils, seasons = _lookups()
    farm = fetch_one("SELECT * FROM FARM WHERE FARM_ID = :fid", {"fid": farm_id})
    if not farm:
        abort(404)

    if request.method == "GET":
        return render_template("add_farm.html", soils=soils, seasons=seasons, farm=farm, editing=True)

    form = request.form
    try:
        land_area = float(form.get("land_area") or 0)
    except ValueError:
        land_area = 0

    errors = []
    farm_name = (form.get("farm_name") or "").strip()
    location = (form.get("location") or "").strip()
    if not farm_name:
        errors.append("Please enter a farm name.")
    if not location:
        errors.append("Please enter a location.")
    if land_area <= 0:
        errors.append("Land area must be greater than zero.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("add_farm.html", soils=soils, seasons=seasons, farm=farm, editing=True, form=form)

    try:
        execute_dml(
            """
            UPDATE FARM SET FARM_NAME=:name, LOCATION=:loc, LAND_AREA_ACRES=:area,
                   SOIL_ID=:soil, IRRIGATION_TYPE=:irr, WATER_AVAILABILITY=:water,
                   CURRENT_SEASON_ID=:season, NOTES=:notes
            WHERE FARM_ID=:fid AND FARMER_ID=:farmer_id
            """,
            {
                "name": farm_name, "loc": location, "area": land_area,
                "soil": int(form.get("soil_id")), "irr": form.get("irrigation_type"),
                "water": form.get("water_availability"),
                "season": int(form.get("season_id")) if form.get("season_id") else None,
                "notes": (form.get("notes") or "").strip() or None,
                "fid": farm_id, "farmer_id": farmer_id,
            },
        )
    except oracledb.DatabaseError:
        logger.exception("Failed to update farm")
        flash("Could not update the farm. Please try again.", "danger")
        return render_template("add_farm.html", soils=soils, seasons=seasons, farm=farm, editing=True, form=form)

    flash("Farm updated successfully.", "success")
    return redirect(url_for("farmer.farms"))


@bp.route("/farms/<int:farm_id>/delete", methods=["POST"])
@login_required
def delete_farm(farm_id):
    farmer_id = session["farmer_id"]
    if not _owns_farm(farm_id, farmer_id):
        abort(403)

    try:
        execute_dml("DELETE FROM FARM WHERE FARM_ID=:fid AND FARMER_ID=:farmer_id",
                     {"fid": farm_id, "farmer_id": farmer_id})
        flash("Farm deleted.", "info")
    except oracledb.DatabaseError:
        logger.exception("Failed to delete farm")
        flash("Could not delete the farm. It may have related records.", "danger")

    return redirect(url_for("farmer.farms"))


# ------------------------- CROP HISTORY -------------------------------

@bp.route("/history")
@login_required
def history():
    farmer_id = session["farmer_id"]
    rows = fetch_all(
        """
        SELECT ch.HISTORY_ID, f.FARM_NAME, c.CROP_NAME, se.SEASON_NAME,
               ch.PLANTING_DATE, ch.HARVEST_DATE, ch.YIELD_QTL, ch.TOTAL_COST,
               ch.REVENUE, ch.PROFIT, ch.NOTES
        FROM CROP_HISTORY ch
        JOIN FARM f ON f.FARM_ID = ch.FARM_ID
        JOIN CROP c ON c.CROP_ID = ch.CROP_ID
        JOIN SEASON se ON se.SEASON_ID = ch.SEASON_ID
        WHERE f.FARMER_ID = :fid
        ORDER BY ch.PLANTING_DATE DESC
        """,
        {"fid": farmer_id},
    )
    farms = fetch_all("SELECT FARM_ID, FARM_NAME FROM FARM WHERE FARMER_ID=:fid", {"fid": farmer_id})
    crops = fetch_all("SELECT CROP_ID, CROP_NAME FROM CROP WHERE IS_ACTIVE=1 ORDER BY CROP_NAME")
    seasons = fetch_all("SELECT SEASON_ID, SEASON_NAME FROM SEASON ORDER BY SEASON_ID")
    return render_template("history.html", history=rows, farms=farms, crops=crops, seasons=seasons)


@bp.route("/history/add", methods=["POST"])
@login_required
def add_history():
    farmer_id = session["farmer_id"]
    form = request.form
    farm_id = form.get("farm_id")

    if not farm_id or not _owns_farm(int(farm_id), farmer_id):
        abort(403)

    try:
        planting_date = datetime.strptime(form.get("planting_date"), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        flash("Please provide a valid planting date.", "danger")
        return redirect(url_for("farmer.history"))

    harvest_date = None
    if form.get("harvest_date"):
        try:
            harvest_date = datetime.strptime(form.get("harvest_date"), "%Y-%m-%d").date()
        except ValueError:
            pass

    def _num(name):
        val = form.get(name)
        try:
            return float(val) if val not in (None, "") else None
        except ValueError:
            return None

    try:
        execute_dml(
            """
            INSERT INTO CROP_HISTORY (HISTORY_ID, FARM_ID, CROP_ID, SEASON_ID, PLANTING_DATE,
                                       HARVEST_DATE, YIELD_QTL, TOTAL_COST, REVENUE, PROFIT, NOTES)
            VALUES (SEQ_CROP_HISTORY_ID.NEXTVAL, :farm_id, :crop_id, :season_id, :planting,
                    :harvest, :yield_qtl, :total_cost, :revenue,
                    NVL(:revenue, 0) - NVL(:total_cost, 0), :notes)
            """,
            {
                "farm_id": int(farm_id), "crop_id": int(form.get("crop_id")),
                "season_id": int(form.get("season_id")), "planting": planting_date,
                "harvest": harvest_date, "yield_qtl": _num("yield_qtl"),
                "total_cost": _num("total_cost"), "revenue": _num("revenue"),
                "notes": (form.get("notes") or "").strip() or None,
            },
        )
        flash("Crop history recorded.", "success")
    except oracledb.DatabaseError:
        logger.exception("Failed to add crop history")
        flash("Could not save this crop history entry.", "danger")

    return redirect(url_for("farmer.history"))


@bp.route("/history/<int:history_id>/delete", methods=["POST"])
@login_required
def delete_history(history_id):
    farmer_id = session["farmer_id"]
    row = fetch_one(
        """
        SELECT ch.HISTORY_ID FROM CROP_HISTORY ch JOIN FARM f ON f.FARM_ID = ch.FARM_ID
        WHERE ch.HISTORY_ID=:hid AND f.FARMER_ID=:farmer_id
        """,
        {"hid": history_id, "farmer_id": farmer_id},
    )
    if not row:
        abort(403)

    execute_dml("DELETE FROM CROP_HISTORY WHERE HISTORY_ID=:hid", {"hid": history_id})
    flash("History entry deleted.", "info")
    return redirect(url_for("farmer.history"))


# ----------------------------- PROFILE --------------------------------

@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    farmer_id = session["farmer_id"]

    if request.method == "GET":
        farmer = fetch_one("SELECT * FROM FARMER WHERE FARMER_ID = :fid", {"fid": farmer_id})
        return render_template("profile.html", farmer=farmer)

    form = request.form
    full_name = (form.get("full_name") or "").strip()
    state = (form.get("state") or "").strip()
    district = (form.get("district") or "").strip()

    if not full_name:
        flash("Name cannot be empty.", "danger")
        return redirect(url_for("farmer.profile"))

    execute_dml(
        "UPDATE FARMER SET FULL_NAME=:name, STATE=:state, DISTRICT=:district WHERE FARMER_ID=:fid",
        {"name": full_name, "state": state or None, "district": district or None, "fid": farmer_id},
    )
    session["farmer_name"] = full_name
    flash("Profile updated.", "success")
    return redirect(url_for("farmer.profile"))
