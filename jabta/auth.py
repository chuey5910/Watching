"""สมัคร → รออนุมัติ → ล็อกอิน (รหัสผ่าน หรืออัตโนมัติด้วยตัวตน Tailscale)"""
import re
from datetime import timedelta

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from .models import db, User, now
from .security import audit, tailscale_identity, client_ip

bp = Blueprint("auth", __name__)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "กรุณาเข้าสู่ระบบก่อน"

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


@login_manager.user_loader
def load_user(user_id):
    u = db.session.get(User, int(user_id))
    if u and u.status == "approved":
        return u
    return None


def _first_user() -> bool:
    return User.query.count() == 0


def try_tailscale_autologin():
    """ถ้ามี header ตัวตนจาก tailscale serve และตรงกับผู้ใช้ที่อนุมัติแล้ว → ล็อกอินให้เลย"""
    if current_user.is_authenticated:
        return None
    ts_login, ts_name = tailscale_identity()
    if not ts_login:
        return None
    u = User.query.filter_by(tailscale_login=ts_login).first()
    if u and u.status == "approved":
        login_user(u, remember=False)
        u.last_login_at = now()
        u.last_login_ip = client_ip()
        audit("login_tailscale", target=u.username, detail=f"อัตโนมัติจาก {ts_login}", user=u)
        return u
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.board"))
    if try_tailscale_autologin():
        return redirect(request.args.get("next") or url_for("main.board"))

    ts_login, ts_name = tailscale_identity()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        u = User.query.filter_by(username=username).first()
        if not u:
            audit("login_fail", target=username, detail="ไม่พบผู้ใช้", ok=False)
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
        elif u.is_locked:
            audit("login_locked", target=username, detail="บัญชีถูกล็อกชั่วคราว", ok=False, user=u)
            flash("บัญชีถูกล็อกชั่วคราวเพราะใส่รหัสผิดหลายครั้ง ลองใหม่ภายหลัง", "error")
        elif not u.check_password(password):
            u.failed_logins = (u.failed_logins or 0) + 1
            if u.failed_logins >= current_app.config["MAX_LOGIN_FAILS"]:
                u.locked_until = now() + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
                u.failed_logins = 0
            db.session.commit()
            audit("login_fail", target=username, detail="รหัสผ่านผิด", ok=False, user=u)
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "error")
        elif u.status == "pending":
            audit("login_pending", target=username, detail="ยังไม่ได้รับอนุมัติ", ok=False, user=u)
            return redirect(url_for("auth.pending", u=u.username))
        elif u.status in ("rejected", "disabled"):
            audit("login_denied", target=username, detail=f"สถานะ {u.status}", ok=False, user=u)
            flash("บัญชีนี้ถูกปฏิเสธหรือระงับการใช้งาน ติดต่อผู้ดูแล", "error")
        else:
            u.failed_logins = 0
            u.locked_until = None
            u.last_login_at = now()
            u.last_login_ip = client_ip()
            # ผูกตัวตน Tailscale ครั้งแรกที่ล็อกอินผ่าน tailscale serve
            if ts_login and not u.tailscale_login:
                u.tailscale_login = ts_login
            db.session.commit()
            login_user(u, remember=bool(request.form.get("remember")))
            audit("login_ok", target=username, user=u)
            nxt = request.args.get("next")
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("main.board"))
    return render_template("auth/login.html", ts_login=ts_login, ts_name=ts_name,
                           registration_open=current_app.config["REGISTRATION_OPEN"])


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.board"))
    if not current_app.config["REGISTRATION_OPEN"] and not _first_user():
        flash("ปิดรับสมัครชั่วคราว ติดต่อผู้ดูแลระบบ", "error")
        return redirect(url_for("auth.login"))

    ts_login, ts_name = tailscale_identity()
    first = _first_user()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        display_name = (request.form.get("display_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        note = (request.form.get("note") or "").strip()
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        errors = []
        if not USERNAME_RE.match(username):
            errors.append("ชื่อผู้ใช้ต้องเป็น a-z 0-9 _ . - ยาว 3–32 ตัว")
        if not display_name:
            errors.append("กรุณาใส่ชื่อที่แสดง")
        if len(pw) < 8:
            errors.append("รหัสผ่านอย่างน้อย 8 ตัวอักษร")
        if pw != pw2:
            errors.append("รหัสผ่านสองช่องไม่ตรงกัน")
        if User.query.filter_by(username=username).first():
            errors.append("ชื่อผู้ใช้นี้มีคนใช้แล้ว")
        if errors:
            for e in errors:
                flash(e, "error")
            audit("register_fail", target=username, detail="; ".join(errors), ok=False)
        else:
            u = User(username=username, display_name=display_name, email=email or None, note=note or None,
                     tailscale_login=ts_login)
            u.set_password(pw)
            if first and current_app.config["FIRST_USER_IS_ADMIN"]:
                u.role, u.status, u.approved_at = "admin", "approved", now()
            db.session.add(u)
            db.session.commit()
            audit("register", target=username,
                  detail=("ผู้ใช้คนแรก → admin อนุมัติอัตโนมัติ" if u.status == "approved" else "รออนุมัติ")
                  + (f" · tailscale={ts_login}" if ts_login else ""), user=u)
            if u.status == "approved":
                login_user(u)
                flash("สร้างบัญชีผู้ดูแลระบบคนแรกเรียบร้อย", "ok")
                return redirect(url_for("main.board"))
            return redirect(url_for("auth.pending", u=u.username))
    return render_template("auth/register.html", ts_login=ts_login, ts_name=ts_name, first=first)


@bp.route("/pending")
def pending():
    username = request.args.get("u", "")
    u = User.query.filter_by(username=username).first() if username else None
    return render_template("auth/pending.html", u=u)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("logout", target=current_user.username)
    logout_user()
    flash("ออกจากระบบแล้ว", "ok")
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        old = request.form.get("old_password") or ""
        new = request.form.get("new_password") or ""
        new2 = request.form.get("new_password2") or ""
        if not current_user.check_password(old):
            flash("รหัสผ่านเดิมไม่ถูกต้อง", "error")
            audit("password_change_fail", target=current_user.username, ok=False)
        elif len(new) < 8 or new != new2:
            flash("รหัสผ่านใหม่ต้องยาวอย่างน้อย 8 ตัวและตรงกันทั้งสองช่อง", "error")
        else:
            current_user.set_password(new)
            db.session.commit()
            audit("password_change", target=current_user.username)
            flash("เปลี่ยนรหัสผ่านแล้ว", "ok")
        return redirect(url_for("auth.account"))
    return render_template("auth/account.html")
