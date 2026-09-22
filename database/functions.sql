-- =====================================================================
-- KRISHIMITRA — STORED FUNCTIONS
-- Run after schema.sql and seed.sql
-- =====================================================================

BEGIN EXECUTE IMMEDIATE 'DROP FUNCTION CALCULATE_CROP_SCORE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP FUNCTION CALCULATE_PROFIT'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP FUNCTION CALCULATE_RISK_SCORE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

-- ---------------------------------------------------------------------
-- CALCULATE_CROP_SCORE
-- The core of the recommendation engine, expressed as a reusable
-- database function so it can also be exercised straight from SQL*Plus
-- for grading/demo purposes, independent of the Flask layer (which
-- also implements the same logic in Python for the What-If simulator's
-- fast in-memory re-scoring — see services/recommendation_engine.py).
--
-- Weights: Soil 25, Season 20, Water 20, Budget 15, Rotation 10,
--          Resource 10  => Total 100
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION CALCULATE_CROP_SCORE (
    p_crop_id         IN CROP.CROP_ID%TYPE,
    p_soil_id         IN SOIL.SOIL_ID%TYPE,
    p_season_id       IN SEASON.SEASON_ID%TYPE,
    p_water_avail     IN VARCHAR2,      -- LOW / MODERATE / HIGH
    p_budget          IN NUMBER,        -- farmer's available budget (INR)
    p_land_area       IN NUMBER,        -- acres
    p_last_crop_id    IN CROP.CROP_ID%TYPE DEFAULT NULL
) RETURN NUMBER
IS
    v_soil_score      NUMBER := 0;
    v_season_score    NUMBER := 0;
    v_water_score     NUMBER := 0;
    v_budget_score    NUMBER := 0;
    v_rotation_score  NUMBER := 0;
    v_resource_score  NUMBER := 0;
    v_suitability     VARCHAR2(10);
    v_crop_water_req  VARCHAR2(10);
    v_cost_per_acre   NUMBER := 0;
    v_total_cost      NUMBER := 0;
BEGIN
    -- Soil compatibility (25)
    BEGIN
        SELECT SUITABILITY_LEVEL INTO v_suitability
        FROM CROP_SOIL WHERE CROP_ID = p_crop_id AND SOIL_ID = p_soil_id;

        v_soil_score := CASE v_suitability
                           WHEN 'EXCELLENT' THEN 25
                           WHEN 'GOOD'      THEN 20
                           WHEN 'FAIR'      THEN 12
                           WHEN 'POOR'      THEN 5
                           ELSE 0 END;
    EXCEPTION WHEN NO_DATA_FOUND THEN v_soil_score := 0; END;

    -- Season compatibility (20)
    SELECT COUNT(*) * 20 INTO v_season_score
    FROM CROP_SEASON WHERE CROP_ID = p_crop_id AND SEASON_ID = p_season_id;

    -- Water compatibility (20) — compares farm's available water to the
    -- crop's requirement; exact match = full score, one band off = partial
    SELECT WATER_REQUIREMENT INTO v_crop_water_req FROM CROP WHERE CROP_ID = p_crop_id;

    v_water_score := CASE
        WHEN v_crop_water_req = p_water_avail THEN 20
        WHEN (v_crop_water_req = 'MODERATE' AND p_water_avail IN ('LOW','HIGH')) THEN 12
        WHEN (v_crop_water_req = 'LOW' AND p_water_avail = 'MODERATE') THEN 16
        WHEN (v_crop_water_req = 'HIGH' AND p_water_avail = 'MODERATE') THEN 10
        WHEN (v_crop_water_req = 'LOW' AND p_water_avail = 'HIGH') THEN 14
        WHEN (v_crop_water_req = 'HIGH' AND p_water_avail = 'LOW') THEN 2
        ELSE 8 END;

    -- Budget compatibility (15) — based on total estimated cost for the
    -- farmer's land area versus their stated budget
    BEGIN
        SELECT COST_PER_ACRE INTO v_cost_per_acre FROM CROP_COST WHERE CROP_ID = p_crop_id;
    EXCEPTION WHEN NO_DATA_FOUND THEN v_cost_per_acre := 0; END;

    v_total_cost := v_cost_per_acre * NVL(p_land_area, 1);

    IF p_budget IS NULL OR v_total_cost = 0 THEN
        v_budget_score := 10;
    ELSIF p_budget >= v_total_cost THEN
        v_budget_score := 15;
    ELSIF p_budget >= v_total_cost * 0.85 THEN
        v_budget_score := 10;
    ELSIF p_budget >= v_total_cost * 0.6 THEN
        v_budget_score := 5;
    ELSE
        v_budget_score := 0;
    END IF;

    -- Crop rotation / history compatibility (10) — penalise repeating the
    -- exact same crop back-to-back (depletes soil, raises disease risk)
    IF p_last_crop_id IS NULL THEN
        v_rotation_score := 8;   -- neutral-positive when no history exists
    ELSIF p_last_crop_id = p_crop_id THEN
        v_rotation_score := 2;   -- discourage monocropping
    ELSE
        v_rotation_score := 10;
    END IF;

    -- Resource compatibility (10) — simple availability proxy: crops with
    -- fewer distinct required resources score slightly higher (lower
    -- logistical burden for the farmer)
    SELECT GREATEST(10 - COUNT(*), 4) INTO v_resource_score
    FROM CROP_RESOURCE WHERE CROP_ID = p_crop_id;

    RETURN ROUND(v_soil_score + v_season_score + v_water_score
                 + v_budget_score + v_rotation_score + v_resource_score, 2);
END CALCULATE_CROP_SCORE;
/

-- ---------------------------------------------------------------------
-- CALCULATE_PROFIT
-- Given a total investment and expected revenue, returns the profit.
-- Kept as a tiny pure function so PROCEDURES/triggers and reports can
-- reuse one canonical definition of "profit".
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION CALCULATE_PROFIT (
    p_revenue    IN NUMBER,
    p_investment IN NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN NVL(p_revenue, 0) - NVL(p_investment, 0);
END CALCULATE_PROFIT;
/

-- ---------------------------------------------------------------------
-- CALCULATE_RISK_SCORE
-- Weighted overall risk (0-100) for a crop, from CROP_RISK rows, with
-- an optional adjustment for the farmer's own water availability
-- (a farm with LOW water raises the effective WATER risk weight).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION CALCULATE_RISK_SCORE (
    p_crop_id     IN CROP.CROP_ID%TYPE,
    p_water_avail IN VARCHAR2 DEFAULT NULL
) RETURN NUMBER
IS
    v_water   NUMBER := 0;
    v_soil    NUMBER := 0;
    v_disease NUMBER := 0;
    v_market  NUMBER := 0;
    v_weather NUMBER := 0;
    v_water_weight NUMBER := 0.25;
    v_score   NUMBER;
BEGIN
    SELECT NVL(MAX(CASE WHEN RISK_TYPE='WATER'   THEN RISK_SCORE END),0),
           NVL(MAX(CASE WHEN RISK_TYPE='SOIL'    THEN RISK_SCORE END),0),
           NVL(MAX(CASE WHEN RISK_TYPE='DISEASE' THEN RISK_SCORE END),0),
           NVL(MAX(CASE WHEN RISK_TYPE='MARKET'  THEN RISK_SCORE END),0),
           NVL(MAX(CASE WHEN RISK_TYPE='WEATHER' THEN RISK_SCORE END),0)
      INTO v_water, v_soil, v_disease, v_market, v_weather
      FROM CROP_RISK WHERE CROP_ID = p_crop_id;

    IF p_water_avail = 'LOW' THEN
        v_water_weight := 0.35;
    ELSIF p_water_avail = 'HIGH' THEN
        v_water_weight := 0.15;
    END IF;

    -- Weights (water weight varies by farm water availability; the
    -- remainder is carried by weather so all weights always sum to 1)
    v_score := (v_water * v_water_weight)
             + (v_soil    * 0.15)
             + (v_disease * 0.20)
             + (v_market  * 0.20)
             + (v_weather * (1 - v_water_weight - 0.15 - 0.20 - 0.20));

    RETURN ROUND(v_score, 2);
END CALCULATE_RISK_SCORE;
/
