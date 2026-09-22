"""
KrishiMitra — Farming Economics calculator.

Total Investment = Seed + Fertilizer + Labour + Irrigation + Other
Expected Revenue = Expected Yield x Selling Price
Profit           = Revenue - Investment
ROI              = Profit / Investment x 100
"""
from db.connection import fetch_one


def get_default_costs(crop_id):
    row = fetch_one(
        """
        SELECT SEED_COST, FERTILIZER_COST, LABOUR_COST, IRRIGATION_COST, OTHER_COST
        FROM CROP_COST WHERE CROP_ID = :cid
        """,
        {"cid": crop_id},
    )
    if not row:
        return {"seed_cost": 0, "fertilizer_cost": 0, "labour_cost": 0, "irrigation_cost": 0, "other_cost": 0}
    return row


def get_crop_yield_price(crop_id):
    row = fetch_one(
        "SELECT EXPECTED_YIELD_QTL_PER_ACRE, AVG_SELLING_PRICE_PER_QTL, CROP_NAME FROM CROP WHERE CROP_ID = :cid",
        {"cid": crop_id},
    )
    return row


def calculate_economics(crop_id, land_area, seed_cost=None, fertilizer_cost=None,
                         labour_cost=None, irrigation_cost=None, other_cost=None,
                         yield_override=None, price_override=None):
    """
    Compute investment/revenue/profit/ROI for a crop over the given
    land area (acres). Any of the per-acre cost components can be
    overridden by the farmer; unspecified ones fall back to the crop's
    stored defaults from CROP_COST.
    """
    defaults = get_default_costs(crop_id)
    crop = get_crop_yield_price(crop_id)
    if not crop:
        raise ValueError("Crop not found")

    seed = seed_cost if seed_cost is not None else float(defaults["seed_cost"] or 0)
    fert = fertilizer_cost if fertilizer_cost is not None else float(defaults["fertilizer_cost"] or 0)
    labour = labour_cost if labour_cost is not None else float(defaults["labour_cost"] or 0)
    irrigation = irrigation_cost if irrigation_cost is not None else float(defaults["irrigation_cost"] or 0)
    other = other_cost if other_cost is not None else float(defaults["other_cost"] or 0)

    per_acre_investment = seed + fert + labour + irrigation + other
    total_investment = round(per_acre_investment * land_area, 2)

    expected_yield = yield_override if yield_override is not None else float(crop["expected_yield_qtl_per_acre"]) * land_area
    price = price_override if price_override is not None else float(crop["avg_selling_price_per_qtl"])

    expected_revenue = round(expected_yield * price, 2)
    profit = round(expected_revenue - total_investment, 2)
    roi = round((profit / total_investment) * 100, 2) if total_investment > 0 else 0.0

    return {
        "crop_name": crop["crop_name"],
        "land_area": land_area,
        "cost_breakdown": {
            "seed": round(seed * land_area, 2),
            "fertilizer": round(fert * land_area, 2),
            "labour": round(labour * land_area, 2),
            "irrigation": round(irrigation * land_area, 2),
            "other": round(other * land_area, 2),
        },
        "total_investment": total_investment,
        "expected_yield_qtl": round(expected_yield, 2),
        "selling_price_per_qtl": price,
        "expected_revenue": expected_revenue,
        "profit": profit,
        "roi_percent": roi,
        "is_profitable": profit > 0,
    }
