"""
KrishiMitra — authentication routes (registration, login, logout) for
both FARMER and ADMIN roles.
"""
import logging
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import oracledb

from db.connection import fetch_one, execute_dml
from services.auth_service import (
    hash_password, verify_password, validate_email, validate_phone,
    validate_password_strength,
)

bp = Blueprint("auth", __name__)
logger = logging.getLogger("krishimitra.auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    state = (request.form.get("state") or "").strip()
    district = (request.form.get("district") or "").strip()

    errors = []
    if not full_name or len(full_name) < 3:
        errors.append("Please enter your full name (at least 3 characters).")
    if not validate_email(email):
        errors.append("Please enter a valid email address.")
    if not validate_phone(phone):
        errors.append("Please enter a valid 10-digit Indian mobile number.")
    pw_problems = validate_password_strength(password)
    if pw_problems:
        errors.append("Password must contain " + ", ".join(pw_problems) + ".")
    if password != confirm_password:
        errors.append("Password and confirm password do not match.")

    if not errors:
        existing = fetch_one("SELECT FARMER_ID FROM FARMER WHERE EMAIL = :email", {"email": email})
        if existing:
            errors.append("An account with this email already exists. Please log in instead.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("register.html", form=request.form)

    try:
        execute_dml(
            """
            INSERT INTO FARMER (FARMER_ID, FULL_NAME, EMAIL, PHONE, PASSWORD_HASH, STATE, DISTRICT)
            VALUES (SEQ_FARMER_ID.NEXTVAL, :full_name, :email, :phone, :pw_hash, :state, :district)
            """,
            {
                "full_name": full_name, "email": email, "phone": phone,
                "pw_hash": hash_password(password), "state": state or None, "district": district or None,
            },
        )
    except oracledb.DatabaseError:
        logger.exception("Registration failed")
        flash("Something went wrong while creating your account. Please try again.", "danger")
        return render_template("register.html", form=request.form)

    flash("Account created successfully! Please log in.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    remember = request.form.get("remember") == "on"

    farmer = fetch_one(
        "SELECT FARMER_ID, FULL_NAME, PASSWORD_HASH, STATUS FROM FARMER WHERE EMAIL = :email",
        {"email": email},
    )

    if not farmer or not verify_password(password, farmer["password_hash"]):
        flash("Invalid email or password.", "danger")
        return render_template("login.html", form=request.form)

    if farmer["status"] != "ACTIVE":
        flash("Your account has been blocked. Please contact support.", "danger")
        return render_template("login.html")

    session.clear()
    session["farmer_id"] = farmer["farmer_id"]
    session["farmer_name"] = farmer["full_name"]
    session.permanent = remember

    flash(f"Welcome back, {farmer['full_name'].split(' ')[0]}!", "success")
    next_url = request.args.get("next")
    return redirect(next_url or url_for("farmer.dashboard"))


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


# ------------------------- ADMIN AUTH -------------------------------

@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    admin = fetch_one(
        "SELECT ADMIN_ID, FULL_NAME, PASSWORD_HASH FROM ADMIN_USER WHERE EMAIL = :email",
        {"email": email},
    )

    if not admin or not verify_password(password, admin["password_hash"]):
        flash("Invalid admin credentials.", "danger")
        return render_template("admin_login.html")

    session.clear()
    session["admin_id"] = admin["admin_id"]
    session["admin_name"] = admin["full_name"]
    flash(f"Welcome, {admin['full_name']}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Admin logged out.", "info")
    return redirect(url_for("auth.admin_login"))
