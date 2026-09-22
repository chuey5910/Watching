import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta, timezone

import click
from flask import Flask, request, g, render_template
from flask_login import current_user

from config import Config
from .models import db, CATEGORIES, LEVELS, SOURCE_TYPES, FETCH_KINDS, USER_STATUS
from .auth import bp as auth_bp, login_manager, try_tailscale_autologin
from .security import enforce_tailscale_gate, client_ip, tailscale_identity
from .views import bp as main_bp


def setup_logging(app: Flask):
    log_dir = app.config["LOG_DIR"]
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger("jabta")
    root.setLevel(app.config["LOG_LEVEL"])
    if not any(getattr(h, "_jabta", False) for h in root.handlers):
        fh = RotatingFileHandler(os.path.join(log_dir, "app.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt); fh._jabta = True
        root.addHandler(fh)
        sh = logging.StreamHandler(); sh.setFormatter(fmt); sh._jabta = True
        root.addHandler(sh)
        # audit log แยกไฟล์ (เก็บนานกว่า)
        ah = RotatingFileHandler(os.path.join(log_dir, "audit.log"), maxBytes=5_000_000, backupCount=20, encoding="utf-8")
        ah.setFormatter(fmt); ah._jabta = True
        alog = logging.getLogger("jabta.audit"); alog.addHandler(ah); alog.propagate = False; alog.setLevel(logging.INFO)
        # access log
        xh = RotatingFileHandler(os.path.join(log_dir, "access.log"), maxBytes=5_000_000, backupCount=10, encoding="utf-8")
        xh.setFormatter(logging.Formatter("%(asctime)s %(message)s")); xh._jabta = True
        xlog = logging.getLogger("jabta.access"); xlog.addHandler(xh); xlog.propagate = False; xlog.setLevel(logging.INFO)


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_object)
    os.makedirs(os.path.dirname(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")) or ".", exist_ok=True)
    setup_logging(app)

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    @app.before_request
    def _gate():
        resp = enforce_tailscale_gate()
        if resp is not None:
            return resp
        # ล็อกอินอัตโนมัติจากตัวตน Tailscale (เมื่อยังไม่ล็อกอิน)
        if request.endpoint and not request.endpoint.startswith("static"):
            try_tailscale_autologin()

    @app.after_request
    def _access_log(resp):
        if not request.path.startswith("/static/"):
            ts, _ = tailscale_identity()
            logging.getLogger("jabta.access").info(
                '%s %s %s %s user=%s ts=%s ua="%s"', client_ip(), request.method, request.full_path.rstrip("?"),
                resp.status_code, getattr(current_user, "username", "-") if current_user else "-", ts or "-",
                request.headers.get("User-Agent", "")[:120])
        return resp

    # ---------- template helpers ----------
    TZ = timezone(timedelta(hours=7))

    def to_local(dt):
        if not dt:
            return None
        return dt.replace(tzinfo=timezone.utc).astimezone(TZ)

    def fmt_time(dt, fmt="%H:%M"):
        l = to_local(dt)
        return l.strftime(fmt) if l else "—"

    def ago(dt):
        if not dt:
            return "—"
        d = datetime.utcnow() - dt
        s = int(d.total_seconds())
        if s < 60:
            return "เมื่อครู่"
        if s < 3600:
            return f"{s // 60} นาที"
        if s < 86400:
            return f"{s // 3600} ชม."
        return f"{s // 86400} วัน"

    THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสฯ", "ศุกร์", "เสาร์", "อาทิตย์"]

    def thai_date(dt=None):
        l = to_local(dt or datetime.utcnow())
        return f"{THAI_DAYS[l.weekday()]} {l.day} {THAI_MONTHS[l.month - 1]} {l.year + 543}"

    from .thaiwrap import thai_zwsp
    app.jinja_env.filters.update(fmt_time=fmt_time, ago=ago, thai_date=thai_date, tw=thai_zwsp)
    app.jinja_env.globals.update(CATEGORIES=CATEGORIES, LEVELS=LEVELS, SOURCE_TYPES=SOURCE_TYPES,
                                 FETCH_KINDS=FETCH_KINDS, USER_STATUS=USER_STATUS, thai_date=thai_date)

    @app.errorhandler(403)
    def _403(e):
        return render_template("error.html", code=403, msg="ไม่อนุญาต — เข้าถึงได้เฉพาะภายใน Tailnet และผู้ใช้ที่ได้รับสิทธิ์"), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("error.html", code=404, msg="ไม่พบหน้าที่ต้องการ"), 404

    # ---------- CLI ----------
    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="ลบแหล่งข่าวเดิมทั้งหมดก่อน")
    def seed_cmd(reset):
        from .seed_sources import seed
        n = seed(reset=reset)
        click.echo(f"เพิ่มแหล่งข่าว {n} รายการ")

    @app.cli.command("fetch")
    @click.option("--source", "source_id", type=int, default=None)
    def fetch_cmd(source_id):
        from .fetcher import run_fetch
        from .rules import apply_rules, expire_pins, send_alerts
        s = run_fetch([source_id] if source_id else None)
        apply_rules(s["kept_ids"]); send_alerts(s["alert_ids"]); expire_pins()
        click.echo(f"แหล่ง {s['sources']} ok={s['ok']} error={s['error']} ใหม่={s['new']} เก็บ={s['kept']}")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    @click.option("--name", default=None)
    def create_admin(username, password, name):
        from .models import User
        u = User.query.filter_by(username=username).first() or User(username=username)
        u.display_name = name or username
        u.set_password(password)
        u.role, u.status = "admin", "approved"
        u.approved_at = datetime.utcnow()
        db.session.add(u); db.session.commit()
        click.echo(f"admin '{username}' พร้อมใช้งาน")

    @app.cli.command("approve")
    @click.argument("username")
    def approve_cmd(username):
        from .models import User
        u = User.query.filter_by(username=username).first()
        if not u:
            raise click.ClickException("ไม่พบผู้ใช้")
        u.status, u.approved_at = "approved", datetime.utcnow()
        db.session.commit()
        click.echo(f"อนุมัติ {username} แล้ว")

    @app.cli.command("morning-brief")
    def brief_cmd():
        from .rules import send_morning_brief
        click.echo(send_morning_brief())

    return app
