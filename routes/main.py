"""KrishiMitra — landing page and misc top-level routes."""
from flask import Blueprint, render_template, session, redirect, url_for

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if session.get("farmer_id"):
        return redirect(url_for("farmer.dashboard"))
    return render_template("index.html")
