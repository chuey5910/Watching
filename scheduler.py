"""งานเบื้องหลัง: ดึงข่าวทุก N นาที, ปลดหมุดอัตโนมัติ, สรุปเช้าเข้า LINE"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from .fetcher import run_fetch
from .rules import apply_rules, expire_pins, send_alerts, send_morning_brief

log = logging.getLogger("jabta.scheduler")
_scheduler: BackgroundScheduler | None = None


def fetch_job(app):
    with app.app_context():
        try:
            summary = run_fetch(app=app)
            apply_rules(summary["kept_ids"])
            send_alerts(summary["alert_ids"])
            expire_pins()
        except Exception:
            log.exception("fetch_job ล้มเหลว")


def start(app):
    global _scheduler
    # กันรันซ้ำเมื่อ Flask debug reloader ทำงาน
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None
    if _scheduler:
        return _scheduler
    tz = app.config.get("TIMEZONE", "Asia/Bangkok")
    sch = BackgroundScheduler(timezone=tz)
    sch.add_job(fetch_job, "interval", minutes=app.config["FETCH_INTERVAL_MINUTES"], args=[app], id="fetch",
                max_instances=1, coalesce=True)
    hh, mm = (app.config.get("MORNING_BRIEF_TIME") or "06:30").split(":")
    sch.add_job(lambda: _with_ctx(app, send_morning_brief), "cron", hour=int(hh), minute=int(mm), id="morning_brief")
    sch.start()
    _scheduler = sch
    log.info("scheduler เริ่มแล้ว: ดึงข่าวทุก %d นาที, สรุปเช้า %s:%s (%s)", app.config["FETCH_INTERVAL_MINUTES"], hh, mm, tz)
    return sch


def _with_ctx(app, fn):
    with app.app_context():
        try:
            fn()
        except Exception:
            log.exception("job %s ล้มเหลว", getattr(fn, "__name__", fn))
