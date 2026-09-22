"""
KrishiMitra — Smart Crop Recommendation Engine.

A transparent, rule-based scoring engine (no external AI APIs). The
exact same weighting model is also implemented as the Oracle function
CALCULATE_CROP_SCORE (database/functions.sql) so a grader can verify
the two independently agree. This Python copy exists so the What-If
Simulator can re-score all crops instantly, in memory, for arbitrary
hypothetical scenarios without writing anything to the database.

Scoring model (100 points total):
    Soil compatibility        25
    Season compatibility      20
    Water compatibility       20
    Budget compatibility      15
    Crop rotation / history   10
    Resource compatibility    10
"""
from db.connection import fetch_all, fetch_one, call_procedure
import oracledb

WEIGHTS = {
    "soil": 25,
    "season": 20,
    "water": 20,
    "budget": 15,
    "rotation": 10,
    "resource": 10,
}

_SOIL_LEVEL_POINTS = {"EXCELLENT": 25, "GOOD": 20, "FAIR": 12, "POOR": 5}

_WATER_MATRIX = {
    # (crop_requirement, farm_availability) -> points out of 20
    ("LOW", "LOW"): 20, ("LOW", "MODERATE"): 16, ("LOW", "HIGH"): 14,
    ("MODERATE", "LOW"): 12, ("MODERATE", "MODERATE"): 20, ("MODERATE", "HIGH"): 12,
    ("HIGH", "LOW"): 2, ("HIGH", "MODERATE"): 10, ("HIGH", "HIGH"): 20,
}


def _get_active_crops():
    return fetch_all("SELECT * FROM CROP WHERE IS_ACTIVE = 1 ORDER BY CROP_NAME")


def _get_crop_soil(crop_id, soil_id):
    return fetch_one(
        "SELECT SUITABILITY_LEVEL FROM CROP_SOIL WHERE CROP_ID=:cid AND SOIL_ID=:sid",
        {"cid": crop_id, "sid": soil_id},
    )


def _crop_has_season(crop_id, season_id):
    row = fetch_one(
        "SELECT COUNT(*) AS cnt FROM CROP_SEASON WHERE CROP_ID=:cid AND SEASON_ID=:sid",
        {"cid": crop_id, "sid": season_id},
    )
    return bool(row and row["cnt"] > 0)


def _crop_cost_per_acre(crop_id):
    row = fetch_one("SELECT COST_PER_ACRE FROM CROP_COST WHERE CROP_ID=:cid", {"cid": crop_id})
    return float(row["cost_per_acre"]) if row and row["cost_per_acre"] is not None else 0.0


def _crop_resource_count(crop_id):
    row = fetch_one(
        "SELECT COUNT(*) AS cnt FROM CROP_RESOURCE WHERE CROP_ID=:cid", {"cid": crop_id}
    )
    return row["cnt"] if row else 0


def _risk_breakdown(crop_id):
    rows = fetch_all(
        "SELECT RISK_TYPE, RISK_SCORE, NOTES FROM CROP_RISK WHERE CROP_ID=:cid", {"cid": crop_id}
    )
    return {r["risk_type"]: {"score": float(r["risk_score"]), "notes": r["notes"]} for r in rows}


def score_crop(crop, soil_id, season_id, water_avail, budget, land_area, last_crop_id=None):
    """
    Score a single crop dict (as returned by _get_active_crops) against
    a farm scenario. Returns a dict with the total score, per-factor
    breakdown, and a list of human-readable explanation bullets.
    """
    crop_id = crop["crop_id"]
    reasons = []

    # --- Soil (25) ---
    cs = _get_crop_soil(crop_id, soil_id)
    if cs:
        level = cs["suitability_level"]
        soil_pts = _SOIL_LEVEL_POINTS.get(level, 0)
        reasons.append((soil_pts >= 20, f"{'Highly suitable' if soil_pts>=20 else 'Somewhat suitable'} for your soil type ({level.title()} match)"))
    else:
        soil_pts = 0
        reasons.append((False, "Not typically grown in your soil type"))

    # --- Season (20) ---
    if _crop_has_season(crop_id, season_id):
        season_pts = WEIGHTS["season"]
        reasons.append((True, "Compatible with your current season"))
    else:
        season_pts = 0
        reasons.append((False, "Not usually grown in your current season"))

    # --- Water (20) ---
    crop_water = crop["water_requirement"]
    water_pts = _WATER_MATRIX.get((crop_water, water_avail), 8)
    if water_pts >= 18:
        reasons.append((True, f"{crop_water.title()} water requirement matches your farm's {water_avail.lower()} availability"))
    elif water_pts >= 10:
        reasons.append((True, f"Manageable water requirement given {water_avail.lower()} availability"))
    else:
        reasons.append((False, f"{crop_water.title()} water requirement is a stretch for {water_avail.lower()} availability"))

    # --- Budget (15) ---
    cost_per_acre = _crop_cost_per_acre(crop_id)
    total_cost = cost_per_acre * (land_area or 1)
    if not budget or total_cost == 0:
        budget_pts = 10
        reasons.append((True, "Budget not specified — assumed adequate"))
    elif budget >= total_cost:
        budget_pts = 15
        reasons.append((True, "Fits comfortably within your available budget"))
    elif budget >= total_cost * 0.85:
        budget_pts = 10
        reasons.append((True, "Close to your available budget"))
    elif budget >= total_cost * 0.6:
        budget_pts = 5
        reasons.append((False, "Somewhat above your stated budget"))
    else:
        budget_pts = 0
        reasons.append((False, "Estimated cost significantly exceeds your budget"))

    # --- Rotation (10) ---
    if last_crop_id is None:
        rotation_pts = 8
        reasons.append((True, "No prior crop on record — neutral rotation impact"))
    elif last_crop_id == crop_id:
        rotation_pts = 2
        reasons.append((False, "Same as your last crop — repeated planting can deplete soil"))
    else:
        rotation_pts = 10
        reasons.append((True, "Good crop rotation compatibility with your last crop"))

    # --- Resource (10) ---
    resource_count = _crop_resource_count(crop_id)
    resource_pts = max(10 - resource_count, 4)
    reasons.append((resource_pts >= 8, "Modest resource/input requirements" if resource_pts >= 8 else "Requires a wider range of inputs"))

    total = round(soil_pts + season_pts + water_pts + budget_pts + rotation_pts + resource_pts, 2)

    risks = _risk_breakdown(crop_id)
    risk_avg = sum(r["score"] for r in risks.values()) / len(risks) if risks else 50
    if risk_avg < 35:
        risk_label = "LOW RISK"
    elif risk_avg < 60:
        risk_label = "MEDIUM RISK"
    else:
        risk_label = "HIGH RISK"

    return {
        "crop_id": crop_id,
        "crop_name": crop["crop_name"],
        "score": total,
        "risk_label": risk_label,
        "risk_avg": round(risk_avg, 1),
        "breakdown": {
            "soil": soil_pts, "season": season_pts, "water": water_pts,
            "budget": budget_pts, "rotation": rotation_pts, "resource": resource_pts,
        },
        "explanation": [text for ok, text in reasons if ok][:5] or [reasons[0][1]],
        "concerns": [text for ok, text in reasons if not ok],
        "estimated_cost": round(total_cost, 2),
        "expected_yield_qtl": float(crop["expected_yield_qtl_per_acre"]) * (land_area or 1),
        "expected_revenue": round(float(crop["expected_yield_qtl_per_acre"]) * (land_area or 1) * float(crop["avg_selling_price_per_qtl"]), 2),
    }


def generate_recommendations(soil_id, season_id, water_avail, budget, land_area, last_crop_id=None, top_n=None):
    """Score every active crop and return them ranked best-first."""
    crops = _get_active_crops()
    scored = [
        score_crop(c, soil_id, season_id, water_avail, budget, land_area, last_crop_id)
        for c in crops
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n] if top_n else scored


def persist_recommendations(farm_id, results, scenario_tag="CURRENT"):
    """
    Save a set of scored results into RECOMMENDATION via the stored
    procedure GENERATE_RECOMMENDATIONS is the "pure DB" path used for
    the demo/viva. The web app instead persists the already-computed
    Python results directly so the UI and the saved audit trail always
    match exactly what the farmer saw on screen.
    """
    from db.connection import get_connection

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM RECOMMENDATION WHERE FARM_ID=:fid AND SCENARIO_TAG=:tag",
            {"fid": farm_id, "tag": scenario_tag},
        )
        for r in results:
            cur.execute(
                """
                INSERT INTO RECOMMENDATION
                    (RECOMMENDATION_ID, FARM_ID, CROP_ID, SUITABILITY_SCORE, RISK_LABEL, EXPLANATION, SCENARIO_TAG)
                VALUES
                    (SEQ_RECOMMENDATION_ID.NEXTVAL, :fid, :cid, :score, :risk, :expl, :tag)
                """,
                {
                    "fid": farm_id,
                    "cid": r["crop_id"],
                    "score": r["score"],
                    "risk": r["risk_label"],
                    "expl": "; ".join(r["explanation"])[:900],
                    "tag": scenario_tag,
                },
            )
    conn.commit()


def run_engine_via_stored_procedure(farm_id, soil_id, season_id, water_avail, budget, land_area, last_crop_id=None, scenario_tag="CURRENT", top_n=5):
    """
    Alternative path that calls the Oracle GENERATE_RECOMMENDATIONS
    stored procedure directly (demonstrates PL/SQL REF CURSOR usage).
    Exposed for the DBMS demo / viva; the main UI uses the Python
    engine above so it can power the What-If simulator without writing
    to the database on every keystroke.
    """
    conn = get_connection = None
    from db.connection import get_connection as _get_conn

    conn = _get_conn()
    with conn.cursor() as cur:
        result_cursor = cur.var(oracledb.DB_TYPE_CURSOR)
        cur.callproc(
            "GENERATE_RECOMMENDATIONS",
            [farm_id, soil_id, season_id, water_avail, budget, land_area,
             last_crop_id, scenario_tag, top_n, result_cursor],
        )
        rows = result_cursor.getvalue().fetchall()
    conn.commit()
    return rows
