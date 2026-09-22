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
    @click.option("--update", is_flag=True, help="ซิงก์ URL/ชนิดการดึงของแหล่งที่มีอยู่แล้วให้ตรงกับ seed_sources.py")
    def seed_cmd(reset, update):
        from .seed_sources import seed
        n = seed(reset=reset, update=update)
        click.echo(f"{'อัปเดต' if update else 'เพิ่ม'}แหล่งข่าว {n} รายการ")

    @app.cli.command("fetch")
    @click.option("--source", "source_id", type=int, default=None)
    def fetch_cmd(source_id):
        from .fetcher import run_fetch
        from .rules import apply_rules, expire_pins, send_alerts
        s = run_fetch([source_id] if source_id else None)
        apply_rules(s["kept_ids"]); send_alerts(s["alert_ids"]); expire_pins()
        click.echo(f"แหล่ง {s['sources']} ok={s['ok']} error={s['error']} ใหม่={s['new']} เก็บ={s['kept']}")

    @app.cli.command("source-report")
    @click.option("--all", "show_all", is_flag=True, help="แสดงทุกแหล่ง ไม่ใช่เฉพาะที่มีปัญหา")
    def source_report_cmd(show_all):
        """สรุปว่าแหล่งไหนดึงจากเว็บตัวเองจริง แหล่งไหนตกไปใช้ Google News แทน

        fetch เขียนว่า ok ได้แม้โดเมนจะตายไปแล้ว เพราะมี fallback ไปหยิบจาก
        Google News ให้อัตโนมัติ ตัวเลข error=0 จึงไม่ได้แปลว่าทุกแหล่งใช้ได้จริง
        """
        from sqlalchemy import func
        from .models import Source, Article

        counts = dict(
            db.session.query(Article.source_id, func.count(Article.id))
            .group_by(Article.source_id).all()
        )
        direct, fellback, empty, errored = [], [], [], []
        for s in Source.query.order_by(Source.source_type, Source.name).all():
            n = counts.get(s.id, 0)
            resolved = s.resolved_feed_url or ""
            if s.last_status == "error":
                errored.append((s, n, s.last_error or ""))
            elif s.fetch_kind in ("gnews", "gnews_query"):
                direct.append((s, n))          # ตั้งใจใช้ Google News ตั้งแต่แรก
            elif "news.google.com" in resolved:
                fellback.append((s, n))        # ตั้งเป็น rss แต่ดึงไม่ได้ เลยตกมาใช้ gnews
            elif n == 0:
                empty.append((s, n))
            else:
                direct.append((s, n))

        click.echo(f"ดึงจากแหล่งเองได้ {len(direct)} · ตกไปใช้ Google News {len(fellback)} "
                   f"· ได้ 0 ข่าว {len(empty)} · error {len(errored)}")
        for label, rows in (("ตกไปใช้ Google News แทน (โดเมนหรือ RSS น่าจะใช้ไม่ได้)", fellback),
                            ("ดึงได้แต่ไม่มีข่าวเลย", empty),
                            ("error", errored)):
            if not rows:
                continue
            click.echo(f"\n--- {label} ({len(rows)}) ---")
            for row in rows:
                s, n = row[0], row[1]
                extra = f"  {row[2][:80]}" if len(row) > 2 else ""
                click.echo(f"{s.id}\t{s.source_type}\t{s.fetch_kind}\t{s.name}\t{s.feed_url}\t{n} ข่าว{extra}")
        if show_all and direct:
            click.echo(f"\n--- ดึงจากแหล่งเองได้ ({len(direct)}) ---")
            for s, n in direct:
                click.echo(f"{s.id}\t{s.source_type}\t{s.fetch_kind}\t{s.name}\t{n} ข่าว")

    @app.cli.command("probe-feeds")
    @click.option("--ids", default="", help="ระบุ id แหล่งข่าวคั่นด้วย , (ว่าง = เลือกเฉพาะแหล่งที่มีปัญหาให้อัตโนมัติ)")
    def probe_feeds_cmd(ids):
        """ลองหา URL ของ RSS ที่ใช้ได้จริงให้แหล่งที่ดึงไม่ได้

        ต้องรันบนเครื่องที่ออกเน็ตได้ ไล่ลองสามทาง: URL ที่ตั้งไว้เดิม,
        <link rel=alternate> ในหน้าแรก, และ path ยอดนิยมอีกชุดใหญ่
        แล้วรายงานว่าอันไหนคืนรายการข่าวได้จริงกี่รายการ
        """
        from urllib.parse import urljoin
        from bs4 import BeautifulSoup
        from sqlalchemy import func
        from .models import Source, Article
        from .fetcher import _session, parse_feed

        PATHS = ["/feed", "/feed/", "/rss", "/rss/", "/rss.xml", "/feed.xml", "/atom.xml",
                 "/index.xml", "/?feed=rss2", "/rss.php", "/rss/news.xml", "/rss/news",
                 "/rss/feed/news", "/rss/latest.xml", "/rss/all.xml", "/rss/home.rss",
                 "/feed/rss", "/rss/feed", "/en/feed", "/en/feed/", "/news/feed",
                 "/rssfeed", "/rss/index.xml", "/api/rss", "/feeds/all.rss"]

        if ids.strip():
            targets = Source.query.filter(Source.id.in_([int(x) for x in ids.split(",") if x.strip()])).all()
        else:
            counts = dict(db.session.query(Article.source_id, func.count(Article.id))
                          .group_by(Article.source_id).all())
            targets = [s for s in Source.query.order_by(Source.id).all()
                       if s.fetch_kind == "rss"
                       and (counts.get(s.id, 0) == 0
                            or "news.google.com" in (s.resolved_feed_url or ""))]
        click.echo(f"สำรวจ {len(targets)} แหล่ง\n")

        sess = _session()

        def try_url(url):
            """คืนจำนวนรายการที่ parse ได้ หรือข้อความบอกว่าพังยังไง"""
            try:
                r = sess.get(url, timeout=15)
                if r.status_code != 200:
                    return None, f"HTTP {r.status_code}"
                n = len(parse_feed(r.content, url))
                return (n, "ok") if n else (0, "ไม่มีรายการ")
            except Exception as ex:
                return None, type(ex).__name__

        for src in targets:
            click.echo(f"=== [{src.id}] {src.name}  ({src.homepage or '-'})")
            seen, good = set(), []
            cands = []
            if src.feed_url:
                cands.append(("เดิม", src.feed_url))
            if src.homepage:
                try:
                    r = sess.get(src.homepage, timeout=15)
                    soup = BeautifulSoup(r.text, "lxml")
                    for l in soup.find_all("link", rel=lambda v: v and "alternate" in v):
                        t = (l.get("type") or "").lower()
                        if ("rss" in t or "atom" in t or "xml" in t) and l.get("href"):
                            cands.append(("ในหน้าแรก", urljoin(src.homepage, l["href"])))
                except Exception as ex:
                    click.echo(f"    เปิดหน้าแรกไม่ได้: {type(ex).__name__}")
                cands += [("ลองเดา", urljoin(src.homepage, p)) for p in PATHS]
            RANK = {"เดิม": 0, "ในหน้าแรก": 1, "ลองเดา": 2}
            for label, url in cands:
                if url in seen or "/comments/" in url:
                    continue          # ฟีดคอมเมนต์ไม่ใช่ฟีดข่าว
                seen.add(url)
                n, msg = try_url(url)
                if n:
                    good.append((n, label, url))
                    click.echo(f"    ใช้ได้  {n:3} รายการ  [{label}] {url}")
            if not good:
                click.echo("    !! ไม่เจอฟีดที่ใช้ได้เลย — ควรเปลี่ยนเป็น fetch_kind=gnews หรือตัดทิ้ง")
            else:
                # ได้ข่าวมากสุดก่อน เท่ากันให้ยึด URL เดิม > ที่เจอในหน้าแรก > ที่เดา
                best = min(good, key=lambda g: (-g[0], RANK.get(g[1], 9), len(g[2])))
                click.echo(f"    >> แนะนำ: {best[2]}" + ("  (เดิมใช้ได้อยู่แล้ว)" if best[1] == "เดิม" else ""))
            click.echo("")

    @app.cli.command("probe-rsshub")
    @click.option("--fb", default="thairath", help="ชื่อเพจ Facebook ที่ใช้ทดสอบ")
    @click.option("--x", "xh", default="Reuters", help="บัญชี X ที่ใช้ทดสอบ")
    @click.option("--tiktok", default="thairath_news", help="บัญชี TikTok ที่ใช้ทดสอบ")
    @click.option("--ig", default="thairath_news", help="บัญชี Instagram ที่ใช้ทดสอบ")
    @click.option("--tg", default="thaigov", help="ช่อง Telegram ที่ใช้ทดสอบ")
    def probe_rsshub_cmd(fb, xh, tiktok, ig, tg):
        """วัดว่า route ไหนของ RSSHub ใช้ได้จริงบนเครือข่ายนี้

        route ของ Facebook / X / Instagram มักถูกแพลตฟอร์มบล็อกหรือบังคับ login
        คำสั่งนี้ยิงจริงแล้วรายงานตามผล จะได้ไม่ต้องเดา
        """
        import requests
        from .fetcher import parse_feed

        base = (app.config.get("RSSHUB_BASE") or "").rstrip("/")
        if not base:
            click.echo("ยังไม่ได้ตั้ง RSSHUB_BASE ใน .env — ตั้งเป็น http://127.0.0.1:1200 ก่อน")
            return
        click.echo(f"RSSHUB_BASE = {base}")
        try:
            r = requests.get(base + "/", timeout=20)
            click.echo(f"ตัว RSSHub เอง: HTTP {r.status_code}\n")
        except Exception as ex:
            click.echo(f"ต่อ RSSHub ไม่ได้: {type(ex).__name__} — ตรวจว่า container rsshub รันอยู่ไหม")
            return

        ROUTES = [
            ("Facebook เพจ",   f"/facebook/page/{fb}"),
            ("X (Twitter)",    f"/twitter/user/{xh}"),
            ("TikTok",         f"/tiktok/user/@{tiktok}"),
            ("Instagram",      f"/picuki/profile/{ig}"),
            ("Instagram (ทางการ)", f"/instagram/user/{ig}"),
            ("Telegram",       f"/telegram/channel/{tg}"),
            ("YouTube",        f"/youtube/user/@{tiktok}"),
        ]
        ok, bad = [], []
        for label, route in ROUTES:
            url = base + route
            try:
                r = requests.get(url, timeout=45)
                if r.status_code != 200:
                    detail = f"HTTP {r.status_code}"
                    # RSSHub ใส่เหตุผลไว้ในเนื้อหาเวลา route พัง
                    txt = (r.text or "")[:160].replace("\n", " ")
                    bad.append((label, route, f"{detail}  {txt}"))
                    click.echo(f"  ใช้ไม่ได้  {label:22} {detail}")
                    continue
                n = len(parse_feed(r.content, url))
                if n:
                    ok.append((label, route, n))
                    click.echo(f"  ใช้ได้     {label:22} {n} รายการ  {route}")
                else:
                    bad.append((label, route, "ตอบ 200 แต่ไม่มีรายการ"))
                    click.echo(f"  ใช้ไม่ได้  {label:22} ตอบ 200 แต่ไม่มีรายการ")
            except Exception as ex:
                bad.append((label, route, type(ex).__name__))
                click.echo(f"  ใช้ไม่ได้  {label:22} {type(ex).__name__}")

        click.echo(f"\nสรุป: ใช้ได้ {len(ok)} · ใช้ไม่ได้ {len(bad)} จาก {len(ROUTES)} route")
        if bad:
            click.echo("\nรายละเอียดที่ใช้ไม่ได้:")
            for label, route, why in bad:
                click.echo(f"  {label:22} {route}\n      {why}")

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
