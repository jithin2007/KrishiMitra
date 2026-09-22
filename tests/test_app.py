"""
KrishiMitra — basic automated tests.

These tests exercise the pure-Python logic (password hashing/validation,
the recommendation scoring model, economics, risk engine) without
requiring a live Oracle connection, plus a set of Flask route smoke
tests using a stubbed database layer.

Run with:  pytest tests/test_app.py -v

Note: the route-level tests monkeypatch db.connection so they can run
without Oracle installed. For a full integration test against a real
Oracle database, point .env at a live instance and remove the monkeypatch
fixtures.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from services.auth_service import (
    hash_password, verify_password, validate_email, validate_phone,
    validate_password_strength,
)


# --------------------------- AUTH SERVICE -----------------------------

def test_password_hash_and_verify():
    hashed = hash_password("StrongPass1!")
    assert hashed != "StrongPass1!"
    assert verify_password("StrongPass1!", hashed)
    assert not verify_password("WrongPass", hashed)


def test_validate_email():
    assert validate_email("farmer@example.com")
    assert not validate_email("not-an-email")
    assert not validate_email("")


def test_validate_phone():
    assert validate_phone("9876543210")
    assert not validate_phone("12345")
    assert not validate_phone("1234567890")  # doesn't start with 6-9


def test_password_strength():
    assert validate_password_strength("Strong1!") == []
    problems = validate_password_strength("weak")
    assert "at least 8 characters" in problems
    assert "one uppercase letter" in problems


# ----------------------- RECOMMENDATION ENGINE -------------------------
# Pure scoring-matrix tests that don't require a DB connection.

def test_water_matrix_exact_match_scores_full():
    from services.recommendation_engine import _WATER_MATRIX
    assert _WATER_MATRIX[("HIGH", "HIGH")] == 20
    assert _WATER_MATRIX[("LOW", "LOW")] == 20


def test_water_matrix_mismatch_scores_low():
    from services.recommendation_engine import _WATER_MATRIX
    assert _WATER_MATRIX[("HIGH", "LOW")] == 2


def test_soil_level_points_ordering():
    from services.recommendation_engine import _SOIL_LEVEL_POINTS
    assert _SOIL_LEVEL_POINTS["EXCELLENT"] > _SOIL_LEVEL_POINTS["GOOD"] > _SOIL_LEVEL_POINTS["FAIR"] > _SOIL_LEVEL_POINTS["POOR"]


# ------------------------------ ECONOMICS -------------------------------

def test_economics_calculation_shape(monkeypatch):
    import services.economics as econ

    monkeypatch.setattr(econ, "get_default_costs", lambda crop_id: {
        "seed_cost": 1000, "fertilizer_cost": 2000, "labour_cost": 3000,
        "irrigation_cost": 1000, "other_cost": 500,
    })
    monkeypatch.setattr(econ, "get_crop_yield_price", lambda crop_id: {
        "expected_yield_qtl_per_acre": 20, "avg_selling_price_per_qtl": 2000, "crop_name": "TestCrop",
    })

    result = econ.calculate_economics(crop_id=1, land_area=2)
    assert result["total_investment"] == 15000  # (1000+2000+3000+1000+500) * 2
    assert result["expected_revenue"] == 80000  # 20*2 * 2000
    assert result["profit"] == 65000
    assert result["is_profitable"] is True


def test_economics_loss_scenario(monkeypatch):
    import services.economics as econ
    monkeypatch.setattr(econ, "get_default_costs", lambda crop_id: {
        "seed_cost": 50000, "fertilizer_cost": 0, "labour_cost": 0, "irrigation_cost": 0, "other_cost": 0,
    })
    monkeypatch.setattr(econ, "get_crop_yield_price", lambda crop_id: {
        "expected_yield_qtl_per_acre": 1, "avg_selling_price_per_qtl": 100, "crop_name": "TestCrop",
    })
    result = econ.calculate_economics(crop_id=1, land_area=1)
    assert result["is_profitable"] is False
    assert result["profit"] < 0


# -------------------------------- RISK ----------------------------------

def test_risk_engine_weights_sum_to_one(monkeypatch):
    import services.risk_engine as risk

    monkeypatch.setattr(risk, "fetch_all", lambda sql, params=None: [
        {"risk_type": "WATER", "risk_score": 50, "notes": None},
        {"risk_type": "SOIL", "risk_score": 20, "notes": None},
        {"risk_type": "DISEASE", "risk_score": 30, "notes": None},
        {"risk_type": "MARKET", "risk_score": 40, "notes": None},
        {"risk_type": "WEATHER", "risk_score": 25, "notes": None},
    ])
    result = risk.get_risk_breakdown(crop_id=1, water_avail="LOW")
    total_weight = sum(result["weights_used"].values())
    assert abs(total_weight - 1.0) < 1e-6
    assert result["label"] in ("LOW RISK", "MEDIUM RISK", "HIGH RISK")


def test_risk_label_thresholds(monkeypatch):
    import services.risk_engine as risk
    monkeypatch.setattr(risk, "fetch_all", lambda sql, params=None: [
        {"risk_type": t, "risk_score": 10, "notes": None} for t in risk.RISK_TYPES
    ])
    result = risk.get_risk_breakdown(crop_id=1)
    assert result["overall_score"] < 35
    assert result["label"] == "LOW RISK"


# ------------------------------ FLASK ROUTES -----------------------------

@pytest.fixture
def client(monkeypatch):
    """A Flask test client with the Oracle pool creation stubbed out."""
    monkeypatch.setattr("db.connection.init_pool", lambda app: None)
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"KrishiMitra" in resp.data


def test_register_page_loads(client):
    resp = client.get("/register")
    assert resp.status_code == 200


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_dashboard_requires_admin_login(client):
    resp = client.get("/admin/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_farm_add_requires_login(client):
    resp = client.get("/farms/add", follow_redirects=False)
    assert resp.status_code == 302


def test_unauthorized_farm_access_returns_403(client, monkeypatch):
    """A farmer must never be able to edit a farm they don't own."""
    with client.session_transaction() as sess:
        sess["farmer_id"] = 1
        sess["farmer_name"] = "Test Farmer"

    monkeypatch.setattr("routes.farmer.fetch_one", lambda sql, params=None: None)
    resp = client.get("/farms/999/edit")
    assert resp.status_code == 403
