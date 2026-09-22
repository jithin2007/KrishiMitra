"""
KrishiMitra — Oracle database connection pool and query helpers.

Uses python-oracledb in "thin" mode by default (pure Python, no Oracle
Instant Client required). Switch ORACLE_CONNECTION_MODE=thick in .env
if you need thick-mode features (and set ORACLE client libs on PATH).

All application SQL goes through get_connection() / execute_query() /
execute_dml() below so that:
  - every query is parameterized (no string-built SQL, no SQL injection)
  - connections are always returned to the pool
  - errors are logged but never leak raw Oracle error text to the UI
"""
import logging
import oracledb
from flask import current_app, g

logger = logging.getLogger("krishimitra.db")

_pool = None


def init_pool(app):
    """Create the Oracle connection pool once, at application startup."""
    global _pool
    if app.config["ORACLE_CONNECTION_MODE"] == "thick":
        oracledb.init_oracle_client()

    _pool = oracledb.create_pool(
        user=app.config["ORACLE_USER"],
        password=app.config["ORACLE_PASSWORD"],
        dsn=app.config["ORACLE_DSN"],
        min=2,
        max=10,
        increment=1,
    )
    logger.info("Oracle connection pool created for DSN %s", app.config["ORACLE_DSN"])


def get_connection():
    """Return a pooled connection for the current request context."""
    if "db_conn" not in g:
        g.db_conn = _pool.acquire()
    return g.db_conn


def close_connection(exception=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        _pool.release(conn)


def register_teardown(app):
    app.teardown_appcontext(close_connection)


def _rows_to_dicts(cursor, rows):
    columns = [col[0].lower() for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def fetch_all(sql, params=None):
    """Run a SELECT and return a list of dicts (column name -> value)."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def fetch_one(sql, params=None):
    results = fetch_all(sql, params)
    return results[0] if results else None


def execute_dml(sql, params=None, commit=True):
    """Run an INSERT/UPDATE/DELETE. Commits by default; rolls back on error."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
        if commit:
            conn.commit()
    except oracledb.DatabaseError:
        conn.rollback()
        logger.exception("DML statement failed, rolled back")
        raise


def call_procedure(name, params=None, keyword_params=None):
    """Call a stored procedure by name with positional/keyword parameters."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            result = cur.callproc(name, params or [], keyword_params or {})
        conn.commit()
        return result
    except oracledb.DatabaseError:
        conn.rollback()
        logger.exception("Procedure %s failed, rolled back", name)
        raise


def call_function(name, return_type, params=None):
    """Call a stored function by name, returning its scalar result."""
    conn = get_connection()
    with conn.cursor() as cur:
        return cur.callfunc(name, return_type, params or [])
