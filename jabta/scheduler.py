"""งานเบื้องหลัง: ดึงข่าวทุก N นาที, ปลดหมุดอัตโนมัติ, สรุปเช้าเข้า LINE"""
import logging
import os
import time

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from apscheduler.schedulers.background import BackgroundScheduler

from .fetcher import run_fetch
from .rules import apply_rules, expire_pins, send_alerts, send_morning_brief

log = logging.getLogger("jabta.scheduler")
_scheduler: BackgroundScheduler | None = None


def fetch_job(app):
    t0 = time.monotonic()
    with app.app_context():
        try:
            summary = run_fetch(app=app)
            apply_rules(summary["kept_ids"])
            send_alerts(summary["alert_ids"])
            expire_pins()
            took = time.monotonic() - t0
            interval = app.config["FETCH_INTERVAL_MINUTES"] * 60
            log.info("fetch_job เสร็จใน %.0f วินาที", took)
            if took > interval:
                # รอบถัดไปจะถูกข้ามเพราะ max_instances=1 ต้องรู้ว่าเกิดขึ้น
                log.warning("fetch_job ใช้เวลา %.0f วินาที นานกว่ารอบดึง %d วินาที "
                            "รอบถัดไปจะถูกข้าม — ควรเพิ่ม FETCH_INTERVAL_MINUTES หรือ FETCH_WORKERS",
                            took, interval)
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
    # misfire_grace_time=None: ถ้าถึงเวลาแล้วเริ่มช้า ให้รันอยู่ดี ไม่ข้ามรอบ
    # ค่าเริ่มต้นของ APScheduler คือ 1 วินาที ซึ่งทำให้รอบถูกทิ้งง่ายมากเมื่อเครื่องยุ่ง
    sch.add_job(fetch_job, "interval", minutes=app.config["FETCH_INTERVAL_MINUTES"], args=[app], id="fetch",
                max_instances=1, coalesce=True, misfire_grace_time=None)
    hh, mm = (app.config.get("MORNING_BRIEF_TIME") or "06:30").split(":")
    sch.add_job(lambda: _with_ctx(app, send_morning_brief), "cron", hour=int(hh), minute=int(mm), id="morning_brief")
    # เดิมเมื่อรอบถูกข้าม (ยังดึงไม่เสร็จ/เริ่มช้า) จะเงียบสนิท ไม่มีทางรู้ว่าเกิดอะไรขึ้น
    sch.add_listener(_on_job_problem, EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)
    sch.start()
    _scheduler = sch
    log.info("scheduler เริ่มแล้ว: ดึงข่าวทุก %d นาที, สรุปเช้า %s:%s (%s)", app.config["FETCH_INTERVAL_MINUTES"], hh, mm, tz)
    return sch


def _on_job_problem(event):
    """บันทึกทุกครั้งที่งานตามเวลาไม่ได้รัน จะได้ไล่หาสาเหตุย้อนหลังได้"""
    if event.code == EVENT_JOB_MAX_INSTANCES:
        log.warning("ข้ามรอบงาน '%s' เพราะรอบก่อนยังทำงานไม่เสร็จ", event.job_id)
    elif event.code == EVENT_JOB_MISSED:
        log.warning("งาน '%s' พลาดรอบที่ %s (เครื่องยุ่งหรือหยุดไปชั่วคราว)", event.job_id, event.scheduled_run_time)
    else:
        log.error("งาน '%s' ล้มเหลว: %s", event.job_id, event.exception)


def status() -> list[dict]:
    """สถานะงานตามเวลา ใช้ตรวจว่า scheduler ยังเดินอยู่จริง"""
    if not _scheduler:
        return []
    return [{"id": j.id, "next_run_at": j.next_run_time} for j in _scheduler.get_jobs()]


def _with_ctx(app, fn):
    with app.app_context():
        try:
            fn()
        except Exception:
            log.exception("job %s ล้มเหลว", getattr(fn, "__name__", fn))
