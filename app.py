"""
KrishiMitra — application entrypoint.

Run with:  python app.py
(or via flask run, with FLASK_APP=app.py)
"""
import logging
from flask import Flask, render_template
import oracledb

from config import Config
from db.connection import init_pool, register_teardown


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    init_pool(app)
    register_teardown(app)

    from routes.main import bp as main_bp
    from routes.auth import bp as auth_bp
    from routes.farmer import bp as farmer_bp
    from routes.crops import bp as crops_bp
    from routes.recommendation import bp as recommendation_bp
    from routes.economics import bp as economics_bp
    from routes.risk import bp as risk_bp
    from routes.admin import bp as admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(farmer_bp)
    app.register_blueprint(crops_bp)
    app.register_blueprint(recommendation_bp)
    app.register_blueprint(economics_bp)
    app.register_blueprint(risk_bp)
    app.register_blueprint(admin_bp)

    register_error_handlers(app)
    return app


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return render_template("errors/500.html"), 500

    @app.errorhandler(oracledb.DatabaseError)
    def database_error(e):
        app.logger.exception("Database error")
        return render_template("errors/500.html"), 500


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
