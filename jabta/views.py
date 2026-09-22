"""หน้าเว็บหลัก: กระดานข่าว, แหล่งข่าว, จัดข่าวเด่น, ผู้ดูแล, log"""
import logging
import re
import secrets
from collections import Counter, defaultdict
from datetime import timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from .models import (db, User, Source, Article, Story, Pin, Rule, Keyword, AuditLog, FetchLog, Setting,
                     CATEGORIES, LEVELS, SOURCE_TYPES, now)
from .security import audit, admin_required, tailscale_identity
from .rules import pin_story, renumber_pins, MAX_PINS, expire_pins, apply_rules, send_alerts, sync_watch_rule
from .fetcher import run_fetch, fetch_source, domain_of
from . import classifier

bp = Blueprint("main", __name__)
log = logging.getLogger("jabta.views")


# ---------- helpers ----------
def _hours():
    try:
        return max(1, min(168, int(request.args.get("h", 24))))
    except ValueError:
        return 24


def _lane_stories(since, category=None, region=None, q=None, limit=10, exclude_ids=()):
    qs = Story.query.filter(Story.last_seen_at >= since)
    if category:
        qs = qs.filter(Story.category == category)
    if exclude_ids:
        qs = qs.filter(~Story.id.in_(list(exclude_ids)))
    if q:
        like = f"%{q}%"
        sub = (db.session.query(Article.story_id)
               .filter(db.or_(Article.title.ilike(like), Article.summary.ilike(like)))
               .subquery())
        qs = qs.filter(db.or_(Story.title.ilike(like), Story.id.in_(db.session.query(sub.c.story_id))))
    if region:
        sub = db.session.query(Article.story_id).filter(Article.region == region).subquery()
        qs = qs.filter(Story.id.in_(sub))
    return qs.order_by(Story.score.desc(), Story.last_seen_at.desc()).limit(limit).all()


def _trending(since):
    """คำสำคัญที่พุ่งขึ้น: เทียบ 24 ชม. ล่าสุดกับ 24 ชม. ก่อนหน้า + คำที่ผู้ใช้ติดตาม"""
    prev = since - (now() - since)
    cur, old = Counter(), Counter()
    for kw, in db.session.query(Article.matched_keywords).filter(Article.fetched_at >= since):
        cur.update(w for w in (kw or "").split(",") if len(w) >= 3)
    for kw, in db.session.query(Article.matched_keywords).filter(Article.fetched_at >= prev, Article.fetched_at < since):
        old.update(w for w in (kw or "").split(",") if len(w) >= 3)
    watch = Keyword.query.filter_by(kind="watch", enabled=True).order_by(Keyword.id.asc()).all()
    out = []
    for w, c in cur.most_common(40):
        o = old.get(w, 0)
        pct = int((c - o) * 100 / o) if o else (100 if c >= 3 else 0)
        out.append({"word": w, "count": c, "pct": pct})
    out.sort(key=lambda x: (-x["pct"], -x["count"]))
    # คำที่ติดตามพิเศษนับตรงจากหัวข้อ
    watch_counts = []
    for k in watch:
        like = f"%{k.word}%"
        c = Article.query.filter(Article.fetched_at >= since,
                                 db.or_(Article.title.ilike(like), Article.summary.ilike(like))).count()
        # ต้องมี id ด้วย เพราะชิปบนกระดานมีปุ่มเลิกเฝ้าระวัง
        watch_counts.append({"id": k.id, "word": k.word, "count": c})
    return out[:8], watch_counts


# ---------- กระดาน ----------
@bp.route("/")
@login_required
def board():
    hours = _hours()
    since = now() - timedelta(hours=hours)
    cat = request.args.get("cat") or None
    q = (request.args.get("q") or "").strip() or None
    region = request.args.get("region") or None

    # พิมพ์ #คำ ในช่องค้นหา = เพิ่มคำนั้นเข้ารายการเฝ้าระวัง แล้วค้นหาด้วยคำนั้นต่อ
    # ใส่หลายคำในครั้งเดียวได้ เช่น "#เหมืองแร่ #ไล่รื้อ"
    if q and "#" in q:
        words = [w.strip() for w in re.findall(r"#([^\s#]+)", q) if w.strip()]
        if words:
            added, dup = [], []
            for w in words:
                if Keyword.query.filter_by(word=w, kind="watch").first():
                    dup.append(w)
                else:
                    db.session.add(Keyword(word=w, kind="watch"))
                    added.append(w)
            if added:
                db.session.commit()
                sync_watch_rule()
                audit("keyword_add", target=",".join(added), detail="เพิ่มจากช่องค้นหาด้วย #")
                flash("เพิ่มคำเฝ้าระวัง: " + ", ".join(added), "ok")
            if dup:
                flash("มีอยู่แล้ว: " + ", ".join(dup), "")
            rest = re.sub(r"#[^\s#]+", " ", q).strip()
            return redirect(url_for("main.board", q=rest or words[0], cat=cat,
                                    h=hours, region=region))

    # ข่าวที่ตรงคำเฝ้าระวัง — ดึงขึ้นเป็นแถบบนสุดเหนือเลนหมวด
    # หมุดมีได้แค่ 5 อัน ที่เหลือต้องไม่หายไปจากสายตา และเลนหมวดด้านล่างยังต้องอยู่ครบ
    # เพื่อให้ยังเห็นความเคลื่อนไหวอย่างอื่นด้วย
    watch_stories = (Story.query.filter(Story.watch_hits.isnot(None), Story.last_seen_at >= since)
                     .order_by(Story.score.desc(), Story.last_seen_at.desc()).limit(12).all())

    pins = Pin.query.order_by(Pin.position.asc()).all()
    pinned_ids = {p.story_id for p in pins}
    hero = pins[0].story if pins else None
    if hero is None:
        top = _lane_stories(since, limit=1)
        hero = top[0] if top else None
    hero_articles = hero.articles.order_by(Article.published_at.desc()).all() if hero else []
    hero_first = hero_articles[-1] if hero_articles else None

    ticker = (Article.query.filter(Article.fetched_at >= now() - timedelta(hours=6), Article.level.in_(["essential", "important"]))
              .order_by(Article.published_at.desc()).limit(10).all())

    # ผลค้นหาเป็นแถบแยกต่างหาก ไม่ไปแทนที่เลนหมวด
    # เลนหมวดคือภาพรวมความเคลื่อนไหวทั้งหมด ถ้าถูกกรองตามคำค้นจะมองไม่เห็นเรื่องอื่นเลย
    search_stories = _lane_stories(since, None, region, q, limit=40) if q else []
    if cat:
        lanes = [(cat, CATEGORIES[cat]["label"],
                  _lane_stories(since, cat, region, None, limit=30, exclude_ids=pinned_ids))]
    else:
        lanes = [(c, CATEGORIES[c]["label"],
                  _lane_stories(since, c, region, None, limit=8, exclude_ids=pinned_ids))
                 for c in CATEGORIES]

    must = {}
    for lvl in LEVELS:
        s = (Story.query.filter(Story.last_seen_at >= since, Story.level == lvl, ~Story.id.in_(list(pinned_ids) or [0]))
             .order_by(Story.score.desc()).first())
        must[lvl] = s

    social = (Article.query.join(Source).filter(Source.source_type == "social", Article.fetched_at >= now() - timedelta(hours=72))
              .order_by(Article.published_at.desc()).limit(12).all())
    social_count = Source.query.filter_by(source_type="social", enabled=True).count()

    trending, watch_counts = _trending(since)

    region_rows = (db.session.query(Article.region, func.count(Article.id)).filter(Article.fetched_at >= since)
                   .group_by(Article.region).order_by(func.count(Article.id).desc()).limit(8).all())
    region_max = max([c for _, c in region_rows] or [1])
    top_sources = (db.session.query(Source, func.count(Article.id)).join(Article).filter(Article.fetched_at >= since)
                   .group_by(Source.id).order_by(func.count(Article.id).desc()).limit(6).all())
    total_sources = Source.query.filter_by(enabled=True).count()
    last_fetch = db.session.query(func.max(Source.last_fetched_at)).scalar()
    total_articles = Article.query.filter(Article.fetched_at >= since).count()

    return render_template("board.html", search_stories=search_stories, watch_stories=watch_stories, pins=pins, hero=hero, hero_articles=hero_articles, hero_first=hero_first,
                           ticker=ticker, lanes=lanes, must=must, social=social, social_count=social_count,
                           trending=trending, watch_counts=watch_counts, region_rows=region_rows, region_max=region_max,
                           top_sources=top_sources, total_sources=total_sources, last_fetch=last_fetch,
                           total_articles=total_articles, hours=hours, cat=cat, q=q, region=region)


@bp.route("/story/<int:story_id>")
@login_required
def story(story_id):
    s = db.session.get(Story, story_id) or abort(404)
    arts = s.articles.order_by(Article.published_at.desc()).all()
    return render_template("story.html", s=s, arts=arts)


# ---------- ปักหมุด ----------
@bp.route("/pin/<int:story_id>", methods=["POST"])
@login_required
def pin(story_id):
    s = db.session.get(Story, story_id) or abort(404)
    top = request.form.get("top") == "1"
    level = request.form.get("level") or "important"
    if Pin.query.count() >= MAX_PINS and not Pin.query.filter_by(story_id=s.id).first():
        flash(f"ปักหมุดได้สูงสุด {MAX_PINS} ข่าว — ปลดหมุดข่าวเก่าก่อน", "error")
        return redirect(request.referrer or url_for("main.board"))
    pin_story(s, level=level, user=current_user, top=top, auto_unpin=request.form.get("auto_unpin") or "idle12h",
              note=request.form.get("note"))
    db.session.commit()
    audit("pin", target=f"story:{s.id}", detail=s.title[:200])
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    flash("ปักหมุดแล้ว", "ok")
    return redirect(request.referrer or url_for("main.board"))


@bp.route("/unpin/<int:story_id>", methods=["POST"])
@login_required
def unpin(story_id):
    p = Pin.query.filter_by(story_id=story_id).first() or abort(404)
    title = p.story.title
    db.session.delete(p)
    renumber_pins()
    db.session.commit()
    audit("unpin", target=f"story:{story_id}", detail=title[:200])
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    flash("ปลดหมุดแล้ว", "ok")
    return redirect(request.referrer or url_for("main.board"))


@bp.route("/pins/reorder", methods=["POST"])
@login_required
def pins_reorder():
    order = request.get_json(silent=True, force=True) or {}
    ids = [int(x) for x in order.get("ids", [])]
    for i, pid in enumerate(ids, start=1):
        p = db.session.get(Pin, pid)
        if p:
            p.position = i
    renumber_pins()
    db.session.commit()
    audit("pin_reorder", detail=",".join(map(str, ids)))
    return jsonify(ok=True)


@bp.route("/pins/<int:pin_id>/update", methods=["POST"])
@login_required
def pin_update(pin_id):
    p = db.session.get(Pin, pin_id) or abort(404)
    p.level = request.form.get("level") or p.level
    p.auto_unpin = request.form.get("auto_unpin") or p.auto_unpin
    if p.auto_unpin == "tomorrow06":
        loc = now() + timedelta(hours=7)
        nxt = (loc + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        p.expires_at = nxt - timedelta(hours=7)
    p.story.level = p.level
    db.session.commit()
    audit("pin_update", target=f"pin:{p.id}", detail=f"level={p.level} auto_unpin={p.auto_unpin}")
    return jsonify(ok=True) if request.headers.get("X-Requested-With") == "fetch" else redirect(url_for("main.curate"))


# ---------- แหล่งข่าว ----------
@bp.route("/sources")
@login_required
def sources():
    t = request.args.get("type") or None
    sort = request.args.get("sort", "today")
    qs = Source.query
    if t:
        qs = qs.filter(Source.source_type == t)
    since = now() - timedelta(hours=24)
    counts = dict(db.session.query(Article.source_id, func.count(Article.id)).filter(Article.fetched_at >= since)
                  .group_by(Article.source_id).all())
    rows = qs.all()
    if sort == "name":
        rows.sort(key=lambda s: s.name)
    elif sort == "new":
        rows.sort(key=lambda s: s.created_at or now(), reverse=True)
    else:
        rows.sort(key=lambda s: (-counts.get(s.id, 0), s.name))
    type_counts = dict(db.session.query(Source.source_type, func.count(Source.id)).group_by(Source.source_type).all())
    groups = sorted({s.group_name for s in Source.query.filter_by(source_type="social") if s.group_name})
    return render_template("sources.html", rows=rows, counts=counts, type_counts=type_counts, t=t, sort=sort,
                           groups=groups, rsshub=bool(current_app.config.get("RSSHUB_BASE")))


def _source_from_form(src: Source | None = None) -> Source:
    f = request.form
    src = src or Source()
    src.name = (f.get("name") or "").strip()
    src.source_type = f.get("source_type") or "mainstream"
    src.fetch_kind = f.get("fetch_kind") or "rss"
    src.homepage = (f.get("homepage") or "").strip() or None
    src.feed_url = (f.get("feed_url") or "").strip() or None
    src.region = (f.get("region") or "ทั่วประเทศ").strip()
    src.country = (f.get("country") or "ไทย").strip()
    src.language = f.get("language") or "th"
    src.platform = (f.get("platform") or "").strip() or None
    src.handle = (f.get("handle") or "").strip() or None
    src.group_name = (f.get("group_name") or "").strip() or None
    cats = f.getlist("categories") or list(CATEGORIES)
    src.categories = ",".join(cats)
    src.keep_all = f.get("keep_all") == "1"
    src.alert_categories = ",".join(f.getlist("alert_categories"))
    src.alert_keywords = (f.get("alert_keywords") or "").strip()
    src.priority = int(f.get("priority") or 0)
    src.enabled = f.get("enabled", "1") == "1"
    if src.source_type == "social":
        src.keep_all = True if f.get("keep_all") is None else src.keep_all
        if src.platform in ("facebook", "x", "tiktok", "instagram") and src.fetch_kind == "rss" and not src.feed_url:
            # ไม่มี RSS ทางการ → ใช้ Google News ค้นชื่อ/handle
            src.fetch_kind = "gnews_query"
            src.feed_url = src.handle or src.name
    return src


@bp.route("/sources/add", methods=["POST"])
@login_required
def source_add():
    src = _source_from_form()
    if not src.name or not (src.homepage or src.feed_url or src.handle):
        flash("ต้องมีชื่อและลิงก์/บัญชีอย่างน้อยหนึ่งอย่าง", "error")
        return redirect(url_for("main.sources"))
    src.created_by_id = current_user.id
    db.session.add(src)
    db.session.commit()
    audit("source_add", target=f"source:{src.id}", detail=f"{src.name} [{src.source_type}/{src.fetch_kind}] {src.feed_url or src.homepage}")
    # ดึงครั้งแรกทันที
    try:
        s = run_fetch([src.id]); apply_rules(s["kept_ids"])
        flash(f"เพิ่ม “{src.name}” แล้ว — ดึงครั้งแรกได้ {s['kept']} ข่าวที่เข้าหมวด (สถานะ: {src.last_status})", "ok")
    except Exception as ex:
        flash(f"เพิ่มแล้ว แต่ดึงครั้งแรกไม่สำเร็จ: {ex}", "error")
    return redirect(url_for("main.sources", type=src.source_type))


@bp.route("/sources/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def source_edit(sid):
    src = db.session.get(Source, sid) or abort(404)
    if request.method == "POST":
        _source_from_form(src)
        src.resolved_feed_url = None
        db.session.commit()
        classifier.reset_cache()
        audit("source_edit", target=f"source:{src.id}", detail=src.name)
        flash("บันทึกแล้ว", "ok")
        return redirect(url_for("main.sources", type=src.source_type))
    groups = sorted({s.group_name for s in Source.query.filter_by(source_type="social") if s.group_name})
    logs = FetchLog.query.filter_by(source_id=sid).order_by(FetchLog.at.desc()).limit(15).all()
    arts = src.articles.order_by(Article.published_at.desc()).limit(20).all()
    return render_template("source_edit.html", src=src, groups=groups, logs=logs, arts=arts,
                           rsshub=bool(current_app.config.get("RSSHUB_BASE")))


@bp.route("/sources/<int:sid>/toggle", methods=["POST"])
@login_required
def source_toggle(sid):
    src = db.session.get(Source, sid) or abort(404)
    src.enabled = not src.enabled
    db.session.commit()
    audit("source_toggle", target=f"source:{sid}", detail=f"{src.name} enabled={src.enabled}")
    return redirect(request.referrer or url_for("main.sources"))


@bp.route("/sources/<int:sid>/delete", methods=["POST"])
@login_required
@admin_required
def source_delete(sid):
    src = db.session.get(Source, sid) or abort(404)
    name = src.name
    db.session.delete(src)
    db.session.commit()
    audit("source_delete", target=f"source:{sid}", detail=name)
    flash(f"ลบ “{name}” แล้ว", "ok")
    return redirect(url_for("main.sources"))


@bp.route("/sources/<int:sid>/fetch", methods=["POST"])
@login_required
def source_fetch(sid):
    src = db.session.get(Source, sid) or abort(404)
    s = run_fetch([sid]); apply_rules(s["kept_ids"])
    src = db.session.get(Source, sid)
    audit("source_fetch", target=f"source:{sid}", detail=f"{src.name} status={src.last_status} kept={s['kept']}")
    flash(f"{src.name}: {src.last_status} · ใหม่ {s['new']} · เก็บ {s['kept']}" + (f" · {src.last_error}" if src.last_error else ""),
          "ok" if src.last_status in ("ok", "empty") else "error")
    return redirect(request.referrer or url_for("main.sources"))


@bp.route("/sources/detect", methods=["POST"])
@login_required
def source_detect():
    """ตรวจลิงก์ที่วางมา: เดาชนิด + ลองดึงตัวอย่าง (ใช้กับปุ่ม 'ตรวจสอบ' ในฟอร์ม)"""
    url = (request.get_json(silent=True, force=True) or {}).get("url", "").strip()
    if not url:
        return jsonify(ok=False, message="ไม่มีลิงก์")
    tmp = Source(name="ตรวจสอบ", source_type="mainstream", fetch_kind="rss", homepage=url, feed_url=None, categories="")
    u = url.lower()
    if "t.me/" in u:
        tmp.fetch_kind, tmp.handle, tmp.platform = "telegram", url.rstrip("/").split("/")[-1], "telegram"
    elif "youtube.com/" in u and ("channel/" in u or "feeds/videos.xml" in u):
        tmp.fetch_kind, tmp.platform = "youtube", "youtube"
        tmp.feed_url = url if "feeds/videos" in u else url.split("channel/")[1].split("/")[0]
    elif "bsky.app/profile/" in u:
        tmp.fetch_kind, tmp.platform = "bluesky", "bluesky"
        tmp.handle = url.split("profile/")[1].split("/")[0]
    elif any(x in u for x in ("facebook.com", "x.com", "twitter.com", "tiktok.com", "instagram.com")):
        plat = "facebook" if "facebook" in u else "tiktok" if "tiktok" in u else "instagram" if "instagram" in u else "x"
        handle = url.rstrip("/").split("/")[-1].split("?")[0]
        base = current_app.config.get("RSSHUB_BASE")
        if base:
            route = {"facebook": f"/facebook/page/{handle}", "x": f"/twitter/user/{handle}", "tiktok": f"/tiktok/user/@{handle}",
                     "instagram": f"/picuki/profile/{handle}"}[plat]
            return jsonify(ok=True, kind="rsshub", platform=plat, handle=handle, feed_url=route, source_type="social",
                           message=f"{plat}: ใช้ RSSHub ที่ตั้งค่าไว้ ({route})")
        return jsonify(ok=True, kind="gnews_query", platform=plat, handle=handle, feed_url=handle, source_type="social",
                       message=f"{plat} ไม่มี RSS ทางการ — จะติดตามผ่านข่าวที่กล่าวถึงบัญชีนี้ (ตั้ง RSSHUB_BASE เพื่อดึงโพสต์ตรง)")
    elif u.endswith((".xml", ".rss", "/feed", "/feed/", ".atom")) or "rss" in u or "feed" in u:
        tmp.feed_url = url
    r = fetch_source(tmp)
    db.session.rollback()
    items = r["items"][:3]
    return jsonify(ok=r["status"] in ("ok", "empty"), kind=tmp.fetch_kind, platform=tmp.platform, handle=tmp.handle,
                   feed_url=tmp.resolved_feed_url or tmp.feed_url or "", homepage=tmp.homepage,
                   message=r["message"] or (f"พบ {len(r['items'])} รายการ" if r["items"] else "ไม่พบรายการ"),
                   sample=[{"title": i["title"], "url": i["url"]} for i in items],
                   source_type="social" if tmp.platform else None)


# ---------- จัดข่าวเด่น ----------
@bp.route("/curate")
@login_required
def curate():
    pins = Pin.query.order_by(Pin.position.asc()).all()
    pinned = {p.story_id for p in pins}
    since = now() - timedelta(hours=12)
    suggestions = (Story.query.filter(Story.last_seen_at >= since, ~Story.id.in_(list(pinned) or [0]))
                   .order_by(Story.score.desc()).limit(8).all())
    rules = Rule.query.order_by(Rule.id.asc()).all()
    watch = Keyword.query.filter_by(kind="watch").order_by(Keyword.id.asc()).all()
    groups = sorted({s.group_name for s in Source.query.filter_by(source_type="social") if s.group_name})
    line_on = bool(current_app.config.get("LINE_CHANNEL_ACCESS_TOKEN") and current_app.config.get("LINE_TO"))
    return render_template("curate.html", pins=pins, suggestions=suggestions, rules=rules, watch=watch, groups=groups,
                           line_on=line_on, max_pins=MAX_PINS, brief_time=current_app.config.get("MORNING_BRIEF_TIME"))


@bp.route("/rules/add", methods=["POST"])
@login_required
def rule_add():
    f = request.form
    r = Rule(name=(f.get("name") or "กฎใหม่").strip(), category=f.get("category") or None,
             min_sources=int(f.get("min_sources") or 1), within_hours=int(f.get("within_hours") or 24),
             keywords=(f.get("keywords") or "").strip() or None, source_type=f.get("source_type") or None,
             source_group=(f.get("source_group") or "").strip() or None, action=f.get("action") or "pin",
             set_level=f.get("set_level") or "important", notify_line=f.get("notify_line") == "1")
    db.session.add(r); db.session.commit()
    audit("rule_add", target=f"rule:{r.id}", detail=r.name)
    flash("เพิ่มกฎแล้ว", "ok")
    return redirect(url_for("main.curate"))


@bp.route("/rules/<int:rid>/toggle", methods=["POST"])
@login_required
def rule_toggle(rid):
    r = db.session.get(Rule, rid) or abort(404)
    r.enabled = not r.enabled
    db.session.commit()
    audit("rule_toggle", target=f"rule:{rid}", detail=f"{r.name} enabled={r.enabled}")
    return jsonify(ok=True, enabled=r.enabled) if request.headers.get("X-Requested-With") == "fetch" else redirect(url_for("main.curate"))


@bp.route("/rules/<int:rid>/delete", methods=["POST"])
@login_required
def rule_delete(rid):
    r = db.session.get(Rule, rid) or abort(404)
    audit("rule_delete", target=f"rule:{rid}", detail=r.name)
    db.session.delete(r); db.session.commit()
    return redirect(url_for("main.curate"))


@bp.route("/keywords/add", methods=["POST"])
@login_required
def keyword_add():
    w = (request.form.get("word") or "").strip()
    if w and not Keyword.query.filter_by(word=w, kind="watch").first():
        db.session.add(Keyword(word=w, kind="watch")); db.session.commit()
        sync_watch_rule()
        audit("keyword_add", target=w)
    return redirect(request.referrer or url_for("main.curate"))


@bp.route("/keywords/<int:kid>/delete", methods=["POST"])
@login_required
def keyword_delete(kid):
    k = db.session.get(Keyword, kid) or abort(404)
    audit("keyword_delete", target=k.word)
    db.session.delete(k); db.session.commit()
    sync_watch_rule()
    return redirect(request.referrer or url_for("main.curate"))


@bp.route("/fetch-now", methods=["POST"])
@login_required
def fetch_now():
    s = run_fetch(); apply_rules(s["kept_ids"]); send_alerts(s["alert_ids"]); expire_pins()
    audit("fetch_now", detail=f"sources={s['sources']} ok={s['ok']} error={s['error']} new={s['new']} kept={s['kept']}")
    flash(f"ดึงข่าวเสร็จ: {s['sources']} แหล่ง · สำเร็จ {s['ok']} · ผิดพลาด {s['error']} · เก็บใหม่ {s['kept']} ข่าว", "ok")
    return redirect(request.referrer or url_for("main.board"))


# ---------- ผู้ดูแล ----------
@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.status.desc(), User.created_at.desc()).all()
    pending = [u for u in users if u.status == "pending"]
    ts_login, _ = tailscale_identity()
    return render_template("admin_users.html", users=users, pending=pending, ts_login=ts_login)


@bp.route("/admin/users/<int:uid>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_user_action(uid, action):
    u = db.session.get(User, uid) or abort(404)
    detail = ""
    if action == "approve":
        u.status, u.approved_at, u.approved_by_id = "approved", now(), current_user.id
    elif action == "reject":
        u.status = "rejected"
    elif action == "disable":
        if u.id == current_user.id:
            flash("ระงับตัวเองไม่ได้", "error"); return redirect(url_for("main.admin_users"))
        u.status = "disabled"
    elif action == "make_admin":
        u.role = "admin"
    elif action == "make_member":
        if u.id == current_user.id:
            flash("ถอดสิทธิ์ตัวเองไม่ได้", "error"); return redirect(url_for("main.admin_users"))
        u.role = "member"
    elif action == "reset_password":
        pw = secrets.token_urlsafe(9)
        u.set_password(pw); u.failed_logins = 0; u.locked_until = None
        detail = "รีเซ็ตรหัสผ่าน"
        flash(f"รหัสผ่านชั่วคราวของ {u.username}: {pw} (แสดงครั้งเดียว)", "ok")
    elif action == "unlock":
        u.failed_logins = 0; u.locked_until = None
    elif action == "clear_tailscale":
        u.tailscale_login = None
    else:
        abort(400)
    db.session.commit()
    audit(f"user_{action}", target=u.username, detail=detail or f"status={u.status} role={u.role}")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/logs")
@login_required
@admin_required
def admin_logs():
    kind = request.args.get("kind", "audit")
    q = (request.args.get("q") or "").strip()
    action = request.args.get("action") or None
    page = max(1, int(request.args.get("page", 1)))
    per = 100
    if kind == "fetch":
        qs = FetchLog.query
        if q:
            qs = qs.join(Source).filter(or_(Source.name.ilike(f"%{q}%"), FetchLog.message.ilike(f"%{q}%")))
        if action:
            qs = qs.filter(FetchLog.status == action)
        rows = qs.order_by(FetchLog.at.desc()).offset((page - 1) * per).limit(per).all()
        actions = [r[0] for r in db.session.query(FetchLog.status).distinct()]
    else:
        qs = AuditLog.query
        if q:
            qs = qs.filter(or_(AuditLog.username.ilike(f"%{q}%"), AuditLog.target.ilike(f"%{q}%"),
                               AuditLog.detail.ilike(f"%{q}%"), AuditLog.ip.ilike(f"%{q}%")))
        if action:
            qs = qs.filter(AuditLog.action == action)
        rows = qs.order_by(AuditLog.at.desc()).offset((page - 1) * per).limit(per).all()
        actions = [r[0] for r in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    stats = {
        "logins_24h": AuditLog.query.filter(AuditLog.action == "login_ok", AuditLog.at >= now() - timedelta(hours=24)).count(),
        "fails_24h": AuditLog.query.filter(AuditLog.action.in_(["login_fail", "login_locked", "blocked_ip"]),
                                           AuditLog.at >= now() - timedelta(hours=24)).count(),
        "fetch_err_24h": FetchLog.query.filter(FetchLog.status == "error", FetchLog.at >= now() - timedelta(hours=24)).count(),
    }
    return render_template("admin_logs.html", rows=rows, kind=kind, q=q, action=action, actions=actions, page=page, stats=stats,
                           log_dir=str(current_app.config["LOG_DIR"]))
