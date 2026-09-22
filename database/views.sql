-- =====================================================================
-- KRISHIMITRA — VIEWS
-- Run after schema.sql and seed.sql
-- =====================================================================

BEGIN EXECUTE IMMEDIATE 'DROP VIEW FARMER_FARM_SUMMARY'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP VIEW CROP_PERFORMANCE_VIEW'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP VIEW ADMIN_CROP_STATISTICS'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP VIEW CROP_RISK_OVERVIEW'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

-- ---------------------------------------------------------------------
-- FARMER_FARM_SUMMARY
-- One row per farmer: farm count, total land, and last activity.
-- Used to power the farmer dashboard's top summary cards.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW FARMER_FARM_SUMMARY AS
SELECT
    f.FARMER_ID,
    f.FULL_NAME,
    f.EMAIL,
    COUNT(fm.FARM_ID)                        AS TOTAL_FARMS,
    NVL(SUM(fm.LAND_AREA_ACRES), 0)          AS TOTAL_LAND_ACRES,
    (SELECT COUNT(*) FROM CROP_HISTORY ch
       JOIN FARM fm2 ON fm2.FARM_ID = ch.FARM_ID
      WHERE fm2.FARMER_ID = f.FARMER_ID
        AND ch.HARVEST_DATE IS NULL)          AS ACTIVE_CROPS,
    (SELECT NVL(SUM(ch.PROFIT), 0) FROM CROP_HISTORY ch
       JOIN FARM fm3 ON fm3.FARM_ID = ch.FARM_ID
      WHERE fm3.FARMER_ID = f.FARMER_ID)       AS TOTAL_PROFIT
FROM FARMER f
LEFT JOIN FARM fm ON fm.FARMER_ID = f.FARMER_ID
GROUP BY f.FARMER_ID, f.FULL_NAME, f.EMAIL;

-- ---------------------------------------------------------------------
-- CROP_PERFORMANCE_VIEW
-- Aggregate real-world performance of each crop across all recorded
-- crop history, joined with the crop's on-paper economics.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW CROP_PERFORMANCE_VIEW AS
SELECT
    c.CROP_ID,
    c.CROP_NAME,
    c.BASE_RISK_LEVEL,
    c.EXPECTED_YIELD_QTL_PER_ACRE,
    c.AVG_SELLING_PRICE_PER_QTL,
    COUNT(ch.HISTORY_ID)                     AS TIMES_PLANTED,
    NVL(AVG(ch.YIELD_QTL), 0)                AS AVG_ACTUAL_YIELD,
    NVL(AVG(ch.PROFIT), 0)                   AS AVG_ACTUAL_PROFIT,
    NVL(SUM(ch.PROFIT), 0)                   AS TOTAL_PROFIT_GENERATED
FROM CROP c
LEFT JOIN CROP_HISTORY ch ON ch.CROP_ID = c.CROP_ID
GROUP BY c.CROP_ID, c.CROP_NAME, c.BASE_RISK_LEVEL, c.EXPECTED_YIELD_QTL_PER_ACRE, c.AVG_SELLING_PRICE_PER_QTL;

-- ---------------------------------------------------------------------
-- ADMIN_CROP_STATISTICS
-- Feeds the admin dashboard's system-wide statistics cards.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW ADMIN_CROP_STATISTICS AS
SELECT
    (SELECT COUNT(*) FROM FARMER)                                   AS TOTAL_FARMERS,
    (SELECT COUNT(*) FROM FARM)                                     AS TOTAL_FARMS,
    (SELECT COUNT(*) FROM CROP WHERE IS_ACTIVE = 1)                 AS TOTAL_CROPS,
    (SELECT COUNT(*) FROM RECOMMENDATION)                           AS TOTAL_RECOMMENDATIONS,
    (SELECT ROUND(AVG(LAND_AREA_ACRES), 2) FROM FARM)               AS AVG_FARM_SIZE,
    (SELECT CROP_NAME FROM (
        SELECT c.CROP_NAME, COUNT(*) cnt FROM CROP_HISTORY ch
        JOIN CROP c ON c.CROP_ID = ch.CROP_ID
        GROUP BY c.CROP_NAME ORDER BY cnt DESC
     ) WHERE ROWNUM = 1)                                            AS MOST_CULTIVATED_CROP,
    (SELECT CROP_NAME FROM (
        SELECT c.CROP_NAME, COUNT(*) cnt FROM RECOMMENDATION r
        JOIN CROP c ON c.CROP_ID = r.CROP_ID
        GROUP BY c.CROP_NAME ORDER BY cnt DESC
     ) WHERE ROWNUM = 1)                                            AS MOST_RECOMMENDED_CROP
FROM DUAL;

-- ---------------------------------------------------------------------
-- CROP_RISK_OVERVIEW
-- Pivoted view: one row per crop with the five risk-type scores as
-- columns, plus an overall average, for quick admin/report display.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW CROP_RISK_OVERVIEW AS
SELECT
    c.CROP_ID,
    c.CROP_NAME,
    MAX(CASE WHEN cr.RISK_TYPE = 'WATER'   THEN cr.RISK_SCORE END) AS WATER_RISK,
    MAX(CASE WHEN cr.RISK_TYPE = 'SOIL'    THEN cr.RISK_SCORE END) AS SOIL_RISK,
    MAX(CASE WHEN cr.RISK_TYPE = 'DISEASE' THEN cr.RISK_SCORE END) AS DISEASE_RISK,
    MAX(CASE WHEN cr.RISK_TYPE = 'MARKET'  THEN cr.RISK_SCORE END) AS MARKET_RISK,
    MAX(CASE WHEN cr.RISK_TYPE = 'WEATHER' THEN cr.RISK_SCORE END) AS WEATHER_RISK,
    ROUND(AVG(cr.RISK_SCORE), 2)                                   AS OVERALL_RISK_SCORE
FROM CROP c
JOIN CROP_RISK cr ON cr.CROP_ID = c.CROP_ID
GROUP BY c.CROP_ID, c.CROP_NAME;
