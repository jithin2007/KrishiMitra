-- =====================================================================
-- KRISHIMITRA — TRIGGERS
-- Run after schema.sql
-- =====================================================================

BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_FARMER_UPDATED_AT'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_FARM_UPDATED_AT'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_CROP_UPDATED_AT'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_CROP_HISTORY_PROFIT'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_BLOCK_FARM_FOR_INACTIVE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TRIGGER TRG_HISTORY_DATE_CHECK'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

-- ---------------------------------------------------------------------
-- TRG_FARMER_UPDATED_AT / TRG_FARM_UPDATED_AT / TRG_CROP_UPDATED_AT
-- Automatically maintain an UPDATED_AT timestamp on every row change,
-- so the application layer never has to remember to set it manually.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER TRG_FARMER_UPDATED_AT
BEFORE UPDATE ON FARMER
FOR EACH ROW
BEGIN
    :NEW.UPDATED_AT := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER TRG_FARM_UPDATED_AT
BEFORE UPDATE ON FARM
FOR EACH ROW
BEGIN
    :NEW.UPDATED_AT := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER TRG_CROP_UPDATED_AT
BEFORE UPDATE ON CROP
FOR EACH ROW
BEGIN
    :NEW.UPDATED_AT := SYSTIMESTAMP;
END;
/

-- ---------------------------------------------------------------------
-- TRG_CROP_HISTORY_PROFIT
-- Whenever TOTAL_COST or REVENUE changes on a crop-history row, keep
-- PROFIT consistent automatically — a safety net beneath RECORD_HARVEST
-- so profit can never silently drift out of sync even if a row is
-- updated by some other path (e.g. an admin correction).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER TRG_CROP_HISTORY_PROFIT
BEFORE INSERT OR UPDATE OF TOTAL_COST, REVENUE ON CROP_HISTORY
FOR EACH ROW
BEGIN
    IF :NEW.REVENUE IS NOT NULL AND :NEW.TOTAL_COST IS NOT NULL THEN
        :NEW.PROFIT := :NEW.REVENUE - :NEW.TOTAL_COST;
    END IF;
END;
/

-- ---------------------------------------------------------------------
-- TRG_HISTORY_DATE_CHECK
-- Extra guard (beyond the table CHECK constraint) that also prevents a
-- planting date set in the future relative to today, and gives a clear
-- application-level error message rather than a generic ORA- error.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER TRG_HISTORY_DATE_CHECK
BEFORE INSERT OR UPDATE OF PLANTING_DATE ON CROP_HISTORY
FOR EACH ROW
BEGIN
    IF :NEW.PLANTING_DATE > SYSDATE + 1 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Planting date cannot be in the future.');
    END IF;
END;
/

-- ---------------------------------------------------------------------
-- TRG_BLOCK_FARM_FOR_INACTIVE
-- Prevents a farm from being inserted for a farmer whose account has
-- been BLOCKED by an admin (invalid state transition guard).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER TRG_BLOCK_FARM_FOR_INACTIVE
BEFORE INSERT ON FARM
FOR EACH ROW
DECLARE
    v_status FARMER.STATUS%TYPE;
BEGIN
    SELECT STATUS INTO v_status FROM FARMER WHERE FARMER_ID = :NEW.FARMER_ID;
    IF v_status != 'ACTIVE' THEN
        RAISE_APPLICATION_ERROR(-20011, 'Cannot add a farm for a blocked farmer account.');
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20012, 'Farmer does not exist.');
END;
/
