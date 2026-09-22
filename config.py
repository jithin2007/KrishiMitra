"""
KrishiMitra — application configuration.

All secrets and environment-specific values are read from environment
variables (see .env.example). Nothing sensitive is hardcoded here.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")

    # Oracle connection details
    ORACLE_USER = os.environ.get("ORACLE_USER", "krishimitra")
    ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "")
    ORACLE_HOST = os.environ.get("ORACLE_HOST", "localhost")
    ORACLE_PORT = os.environ.get("ORACLE_PORT", "1521")
    ORACLE_SERVICE = os.environ.get("ORACLE_SERVICE", "XEPDB1")
    ORACLE_DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
    ORACLE_CONNECTION_MODE = os.environ.get("ORACLE_CONNECTION_MODE", "thin")

    # Session / security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # Recommendation engine weights (kept configurable in one place so
    # both the Flask engine and documentation stay in sync)
    SCORE_WEIGHTS = {
        "soil": 25,
        "season": 20,
        "water": 20,
        "budget": 15,
        "rotation": 10,
        "resource": 10,
    }
