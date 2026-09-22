"""
KrishiMitra — Admin routes: system dashboard, farmer/farm oversight,
and full management of crops, soils, seasons, crop-soil / crop-season
compatibility, crop costs, and crop risk factors.
"""
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
import oracledb

from db.connection import fetch_all, fetch_one, execute_dml
from services.auth_service import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")
logger = logging.getLogger("krishimitra.admin")


@bp.route("/dashboard")
@admin_required
def dashboard():
    stats = fetch_one("SELECT * FROM ADMIN_CROP_STATISTICS")
    crop_performance = fetch_all(
        "SELECT * FROM CROP_PERFORMANCE_VIEW ORDER BY TIMES_PLANTED DESC FETCH FIRST 6 ROWS ONLY"
    )
    recent_farmers = fetch_all(
        "SELECT FARMER_ID, FULL_NAME, EMAIL, STATUS, CREATED_AT FROM FARMER ORDER BY CREATED_AT DESC FETCH FIRST 5 ROWS ONLY"
    )
    return render_template("admin_dashboard.html", stats=stats, crop_performance=crop_performance, recent_farmers=recent_farmers)


# ------------------------------ FARMERS -------------------------------

@bp.route("/farmers")
@admin_required
def farmers():
    rows = fetch_all("SELECT * FROM FARMER_FARM_SUMMARY ORDER BY FULL_NAME")
    statuses = fetch_all(
        "SELECT FARMER_ID, STATUS FROM FARMER"
    )
    status_map = {r["farmer_id"]: r["status"] for r in statuses}
    return render_template("admin_farmers.html", farmers=rows, status_map=status_map)


@bp.route("/farmers/<int:farmer_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_farmer_status(farmer_id):
    farmer = fetch_one("SELECT STATUS FROM FARMER WHERE FARMER_ID = :fid", {"fid": farmer_id})
    if not farmer:
        abort(404)
    new_status = "BLOCKED" if farmer["status"] == "ACTIVE" else "ACTIVE"
    execute_dml("UPDATE FARMER SET STATUS = :s WHERE FARMER_ID = :fid", {"s": new_status, "fid": farmer_id})
    flash(f"Farmer status changed to {new_status}.", "info")
    return redirect(url_for("admin.farmers"))


# -------------------------------- FARMS --------------------------------

@bp.route("/farms")
@admin_required
def farms():
    rows = fetch_all(
        """
        SELECT fm.FARM_ID, fm.FARM_NAME, f.FULL_NAME AS FARMER_NAME, fm.LOCATION,
               fm.LAND_AREA_ACRES, s.SOIL_NAME, fm.IRRIGATION_TYPE, fm.WATER_AVAILABILITY
        FROM FARM fm JOIN FARMER f ON f.FARMER_ID = fm.FARMER_ID JOIN SOIL s ON s.SOIL_ID = fm.SOIL_ID
        ORDER BY fm.CREATED_AT DESC
        """
    )
    return render_template("admin_farms.html", farms=rows)


# -------------------------------- CROPS --------------------------------

@bp.route("/crops")
@admin_required
def crops():
    rows = fetch_all("SELECT * FROM CROP ORDER BY CROP_NAME")
    return render_template("admin_crops.html", crops=rows)


@bp.route("/crops/add", methods=["GET", "POST"])
@admin_required
def add_crop():
    if request.method == "GET":
        return render_template("admin_crop_form.html", crop=None)

    form = request.form
    try:
        execute_dml(
            """
            INSERT INTO CROP (CROP_ID, CROP_NAME, DESCRIPTION, WATER_REQUIREMENT, GROWTH_DURATION_DAYS,
                               EXPECTED_YIELD_QTL_PER_ACRE, AVG_SELLING_PRICE_PER_QTL, BASE_RISK_LEVEL)
            VALUES (SEQ_CROP_ID.NEXTVAL, :name, :desc, :water, :duration, :yield_qtl, :price, :risk)
            """,
            {
                "name": form.get("crop_name"), "desc": form.get("description"),
                "water": form.get("water_requirement"), "duration": int(form.get("growth_duration_days")),
                "yield_qtl": float(form.get("expected_yield")), "price": float(form.get("selling_price")),
                "risk": form.get("base_risk_level"),
            },
        )
        flash("Crop added.", "success")
    except (oracledb.DatabaseError, TypeError, ValueError):
        logger.exception("Failed to add crop")
        flash("Could not add crop. Check the values and try again (crop name must be unique).", "danger")
        return render_template("admin_crop_form.html", crop=None, form=form)

    return redirect(url_for("admin.crops"))


@bp.route("/crops/<int:crop_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_crop(crop_id):
    crop = fetch_one("SELECT * FROM CROP WHERE CROP_ID = :cid", {"cid": crop_id})
    if not crop:
        abort(404)

    if request.method == "GET":
        return render_template("admin_crop_form.html", crop=crop)

    form = request.form
    try:
        execute_dml(
            """
            UPDATE CROP SET CROP_NAME=:name, DESCRIPTION=:desc, WATER_REQUIREMENT=:water,
                   GROWTH_DURATION_DAYS=:duration, EXPECTED_YIELD_QTL_PER_ACRE=:yield_qtl,
                   AVG_SELLING_PRICE_PER_QTL=:price, BASE_RISK_LEVEL=:risk
            WHERE CROP_ID=:cid
            """,
            {
                "name": form.get("crop_name"), "desc": form.get("description"),
                "water": form.get("water_requirement"), "duration": int(form.get("growth_duration_days")),
                "yield_qtl": float(form.get("expected_yield")), "price": float(form.get("selling_price")),
                "risk": form.get("base_risk_level"), "cid": crop_id,
            },
        )
        flash("Crop updated.", "success")
    except (oracledb.DatabaseError, TypeError, ValueError):
        logger.exception("Failed to update crop")
        flash("Could not update crop.", "danger")
        return render_template("admin_crop_form.html", crop=crop, form=form)

    return redirect(url_for("admin.crops"))


@bp.route("/crops/<int:crop_id>/delete", methods=["POST"])
@admin_required
def delete_crop(crop_id):
    # Soft delete: keep historical/recommendation integrity intact.
    execute_dml("UPDATE CROP SET IS_ACTIVE = 0 WHERE CROP_ID = :cid", {"cid": crop_id})
    flash("Crop deactivated.", "info")
    return redirect(url_for("admin.crops"))


@bp.route("/crops/<int:crop_id>/compatibility", methods=["GET", "POST"])
@admin_required
def crop_compatibility(crop_id):
    crop = fetch_one("SELECT * FROM CROP WHERE CROP_ID = :cid", {"cid": crop_id})
    if not crop:
        abort(404)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_soil":
            execute_dml(
                """
                MERGE INTO CROP_SOIL cs USING DUAL ON (cs.CROP_ID=:cid AND cs.SOIL_ID=:sid)
                WHEN MATCHED THEN UPDATE SET SUITABILITY_LEVEL=:level
                WHEN NOT MATCHED THEN INSERT (CROP_ID, SOIL_ID, SUITABILITY_LEVEL) VALUES (:cid, :sid, :level)
                """,
                {"cid": crop_id, "sid": int(request.form.get("soil_id")), "level": request.form.get("suitability_level")},
            )
        elif action == "remove_soil":
            execute_dml("DELETE FROM CROP_SOIL WHERE CROP_ID=:cid AND SOIL_ID=:sid",
                        {"cid": crop_id, "sid": int(request.form.get("soil_id"))})
        elif action == "add_season":
            execute_dml(
                """
                MERGE INTO CROP_SEASON cn USING DUAL ON (cn.CROP_ID=:cid AND cn.SEASON_ID=:seid)
                WHEN NOT MATCHED THEN INSERT (CROP_ID, SEASON_ID) VALUES (:cid, :seid)
                """,
                {"cid": crop_id, "seid": int(request.form.get("season_id"))},
            )
        elif action == "remove_season":
            execute_dml("DELETE FROM CROP_SEASON WHERE CROP_ID=:cid AND SEASON_ID=:seid",
                        {"cid": crop_id, "seid": int(request.form.get("season_id"))})
        elif action == "save_cost":
            execute_dml(
                """
                MERGE INTO CROP_COST cc USING DUAL ON (cc.CROP_ID=:cid)
                WHEN MATCHED THEN UPDATE SET SEED_COST=:seed, FERTILIZER_COST=:fert, LABOUR_COST=:lab,
                     IRRIGATION_COST=:irr, OTHER_COST=:oth
                WHEN NOT MATCHED THEN INSERT (CROP_COST_ID, CROP_ID, SEED_COST, FERTILIZER_COST, LABOUR_COST, IRRIGATION_COST, OTHER_COST)
                     VALUES (SEQ_CROP_COST_ID.NEXTVAL, :cid, :seed, :fert, :lab, :irr, :oth)
                """,
                {
                    "cid": crop_id, "seed": float(request.form.get("seed_cost") or 0),
                    "fert": float(request.form.get("fertilizer_cost") or 0),
                    "lab": float(request.form.get("labour_cost") or 0),
                    "irr": float(request.form.get("irrigation_cost") or 0),
                    "oth": float(request.form.get("other_cost") or 0),
                },
            )
        elif action == "save_risk":
            execute_dml(
                """
                MERGE INTO CROP_RISK cr USING DUAL ON (cr.CROP_ID=:cid AND cr.RISK_TYPE=:rtype)
                WHEN MATCHED THEN UPDATE SET RISK_SCORE=:score, NOTES=:notes
                WHEN NOT MATCHED THEN INSERT (CROP_RISK_ID, CROP_ID, RISK_TYPE, RISK_SCORE, NOTES)
                     VALUES (SEQ_CROP_RISK_ID.NEXTVAL, :cid, :rtype, :score, :notes)
                """,
                {
                    "cid": crop_id, "rtype": request.form.get("risk_type"),
                    "score": float(request.form.get("risk_score")), "notes": request.form.get("notes"),
                },
            )
        flash("Saved.", "success")
        return redirect(url_for("admin.crop_compatibility", crop_id=crop_id))

    soils = fetch_all("SELECT SOIL_ID, SOIL_NAME FROM SOIL ORDER BY SOIL_NAME")
    seasons = fetch_all("SELECT SEASON_ID, SEASON_NAME FROM SEASON ORDER BY SEASON_ID")
    crop_soils = fetch_all(
        "SELECT s.SOIL_ID, s.SOIL_NAME, cs.SUITABILITY_LEVEL FROM CROP_SOIL cs JOIN SOIL s ON s.SOIL_ID=cs.SOIL_ID WHERE cs.CROP_ID=:cid",
        {"cid": crop_id},
    )
    crop_seasons = fetch_all(
        "SELECT se.SEASON_ID, se.SEASON_NAME FROM CROP_SEASON cn JOIN SEASON se ON se.SEASON_ID=cn.SEASON_ID WHERE cn.CROP_ID=:cid",
        {"cid": crop_id},
    )
    cost = fetch_one("SELECT * FROM CROP_COST WHERE CROP_ID=:cid", {"cid": crop_id})
    risks = fetch_all("SELECT * FROM CROP_RISK WHERE CROP_ID=:cid", {"cid": crop_id})

    return render_template(
        "admin_crop_compat.html", crop=crop, soils=soils, seasons=seasons,
        crop_soils=crop_soils, crop_seasons=crop_seasons, cost=cost, risks=risks,
    )


# ------------------------------ LOOKUPS ---------------------------------

@bp.route("/soils", methods=["GET", "POST"])
@admin_required
def soils():
    if request.method == "POST":
        execute_dml(
            "INSERT INTO SOIL (SOIL_ID, SOIL_NAME, DESCRIPTION) VALUES (SEQ_SOIL_ID.NEXTVAL, :name, :desc)",
            {"name": request.form.get("soil_name"), "desc": request.form.get("description")},
        )
        flash("Soil type added.", "success")
        return redirect(url_for("admin.soils"))

    rows = fetch_all("SELECT * FROM SOIL ORDER BY SOIL_NAME")
    return render_template("admin_lookups.html", kind="Soil Type", rows=rows, add_endpoint="admin.soils")


@bp.route("/seasons", methods=["GET", "POST"])
@admin_required
def seasons():
    if request.method == "POST":
        execute_dml(
            """
            INSERT INTO SEASON (SEASON_ID, SEASON_NAME, DESCRIPTION, START_MONTH, END_MONTH)
            VALUES (SEQ_SEASON_ID.NEXTVAL, :name, :desc, :start, :end)
            """,
            {
                "name": request.form.get("season_name"), "desc": request.form.get("description"),
                "start": int(request.form.get("start_month")), "end": int(request.form.get("end_month")),
            },
        )
        flash("Season added.", "success")
        return redirect(url_for("admin.seasons"))

    rows = fetch_all("SELECT * FROM SEASON ORDER BY SEASON_ID")
    return render_template("admin_lookups.html", kind="Season", rows=rows, add_endpoint="admin.seasons")


# --------------------------- RECOMMENDATIONS -----------------------------

@bp.route("/recommendations")
@admin_required
def recommendations():
    rows = fetch_all(
        """
        SELECT r.RECOMMENDATION_ID, f.FULL_NAME AS FARMER_NAME, fm.FARM_NAME, c.CROP_NAME,
               r.SUITABILITY_SCORE, r.RISK_LABEL, r.SCENARIO_TAG, r.CREATED_AT
        FROM RECOMMENDATION r
        JOIN FARM fm ON fm.FARM_ID = r.FARM_ID
        JOIN FARMER f ON f.FARMER_ID = fm.FARMER_ID
        JOIN CROP c ON c.CROP_ID = r.CROP_ID
        ORDER BY r.CREATED_AT DESC FETCH FIRST 100 ROWS ONLY
        """
    )
    return render_template("admin_recommendations.html", recommendations=rows)
