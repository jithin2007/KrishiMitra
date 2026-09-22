"""KrishiMitra — crop library browsing routes."""
from flask import Blueprint, render_template, abort
from db.connection import fetch_all, fetch_one
from services.auth_service import login_required

bp = Blueprint("crops", __name__)


@bp.route("/crops")
@login_required
def crop_list():
    crops = fetch_all(
        """
        SELECT CROP_ID, CROP_NAME, DESCRIPTION, WATER_REQUIREMENT, BASE_RISK_LEVEL,
               GROWTH_DURATION_DAYS, EXPECTED_YIELD_QTL_PER_ACRE, AVG_SELLING_PRICE_PER_QTL
        FROM CROP WHERE IS_ACTIVE = 1 ORDER BY CROP_NAME
        """
    )
    return render_template("crops.html", crops=crops)


@bp.route("/crops/<int:crop_id>")
@login_required
def crop_detail(crop_id):
    crop = fetch_one("SELECT * FROM CROP WHERE CROP_ID = :cid AND IS_ACTIVE = 1", {"cid": crop_id})
    if not crop:
        abort(404)

    soils = fetch_all(
        """
        SELECT s.SOIL_NAME, cs.SUITABILITY_LEVEL FROM CROP_SOIL cs
        JOIN SOIL s ON s.SOIL_ID = cs.SOIL_ID WHERE cs.CROP_ID = :cid ORDER BY cs.SUITABILITY_LEVEL
        """,
        {"cid": crop_id},
    )
    seasons = fetch_all(
        """
        SELECT se.SEASON_NAME FROM CROP_SEASON cn JOIN SEASON se ON se.SEASON_ID = cn.SEASON_ID
        WHERE cn.CROP_ID = :cid
        """,
        {"cid": crop_id},
    )
    cost = fetch_one("SELECT * FROM CROP_COST WHERE CROP_ID = :cid", {"cid": crop_id})
    resources = fetch_all(
        """
        SELECT r.RESOURCE_NAME, r.RESOURCE_TYPE, cr.QTY_PER_ACRE, r.UNIT FROM CROP_RESOURCE cr
        JOIN RESOURCE_ITEM r ON r.RESOURCE_ID = cr.RESOURCE_ID WHERE cr.CROP_ID = :cid
        """,
        {"cid": crop_id},
    )
    risks = fetch_all("SELECT RISK_TYPE, RISK_SCORE, NOTES FROM CROP_RISK WHERE CROP_ID = :cid", {"cid": crop_id})

    expected_revenue = float(crop["expected_yield_qtl_per_acre"]) * float(crop["avg_selling_price_per_qtl"])
    estimated_cost = float(cost["cost_per_acre"]) if cost else 0

    return render_template(
        "crop_detail.html", crop=crop, soils=soils, seasons=seasons, cost=cost,
        resources=resources, risks=risks, expected_revenue=expected_revenue,
        estimated_cost=estimated_cost,
    )
