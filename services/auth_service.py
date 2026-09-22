"""
KrishiMitra — authentication helpers: password hashing/verification and
role-based access decorators.
"""
import re
import functools
import bcrypt
from flask import session, redirect, url_for, flash, request

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian 10-digit mobile numbers


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_email(email: str) -> bool:
    return bool(email) and bool(EMAIL_RE.match(email.strip()))


def validate_phone(phone: str) -> bool:
    return bool(phone) and bool(PHONE_RE.match(phone.strip()))


def validate_password_strength(password: str):
    """Returns a list of unmet requirements; empty list means it's strong enough."""
    problems = []
    if len(password or "") < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Z]", password or ""):
        problems.append("one uppercase letter")
    if not re.search(r"[a-z]", password or ""):
        problems.append("one lowercase letter")
    if not re.search(r"\d", password or ""):
        problems.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        problems.append("one special character")
    return problems


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("farmer_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Admin login required.", "warning")
            return redirect(url_for("auth.admin_login"))
        return view(*args, **kwargs)
    return wrapped
