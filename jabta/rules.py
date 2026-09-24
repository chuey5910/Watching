"""กฎปักหมุดอัตโนมัติ, ปลดหมุดอัตโนมัติ, และการแจ้งเตือน LINE"""
import logging
from datetime import timedelta

from flask import current_app

from .models import db, Story, Pin, Rule, Article, Source, Setting, Keyword, LEVELS, CATEGORIES, now
from .line import push_text

log = logging.getLogger("jabta.rules")

MAX_PINS = 0  # ค่าสำรองเมื่อไม่มี app context — 0 = ไม่จำกัด


def max_pins() -> int:
    """จำนวนหมุดสูงสุดจากค่าตั้ง — 0 หรือติดลบ = ไม่จำกัด"""
    try:
        from flask import current_app
        return int(current_app.config.get("MAX_PINS", MAX_PINS) or 0)
    except Exception:
        return MAX_PINS


WATCH_RULE_NAME = "คำเฝ้าระวัง (ระบบจัดการให้)"


def sync_watch_rule():
    """ให้กฎปักหมุดอัตโนมัติสะท้อนรายการคำเฝ้าระวังปัจจุบันเสมอ

    เรียกทุกครั้งที่ผู้ใช้เพิ่ม/ลบคำเฝ้าระวัง กฎนี้ทำให้ข่าวที่มีคำเหล่านั้น
    ถูกดันขึ้นหมุดอันดับ 1 และส่งแจ้งเตือน LINE โดยไม่ต้องตั้งกฎเอง
    ตัวกฎยังแก้ได้ตามปกติในหน้าจัดข่าวเด่น แต่ช่องคำจะถูกเขียนทับทุกครั้งที่ซิงก์
    """
    words = [k.word.strip() for k in Keyword.query.filter_by(kind="watch", enabled=True).all() if k.word.strip()]
    rule = Rule.query.filter_by(name=WATCH_RULE_NAME).first()
    if not words:
        if rule:
            rule.enabled = False
            db.session.commit()
        return rule
    if not rule:
        rule = Rule(name=WATCH_RULE_NAME)
        db.session.add(rule)
    joined = ",".join(words)
    if len(joined) > 500:
        # ช่อง keywords เก็บได้ 500 ตัวอักษร — บอกให้รู้ว่าคำท้าย ๆ ตกหล่น
        log.warning("คำเฝ้าระวังยาวเกิน 500 ตัวอักษร คำท้าย ๆ จะไม่ถูกใช้ในกฎปักหมุด (%d คำ)", len(words))
    rule.keywords = joined[:500]
    rule.enabled = True
    rule.category = None          # ทุกหมวด รวมข่าวที่ไม่เข้าหมวดด้วย
    rule.min_sources = 1          # แหล่งเดียวก็พอ ไม่ต้องรอให้หลายสื่อรายงาน
    rule.within_hours = 24
    rule.action = "pin_top"
    rule.set_level = "essential"
    rule.notify_line = True
    db.session.commit()
    return rule


def _story_matches(rule: Rule, story: Story) -> bool:
    if rule.category and story.category != rule.category:
        return False
    since = now() - timedelta(hours=rule.within_hours or 24)
    arts = [a for a in story.articles.all() if (a.published_at or a.fetched_at) >= since]
    if not arts:
        return False
    if rule.source_type:
        arts_t = [a for a in arts if a.source and a.source.source_type == rule.source_type]
        if not arts_t:
            return False
        if rule.source_group:
            arts_t = [a for a in arts_t if (a.source.group_name or "") == rule.source_group]
            if not arts_t:
                return False
    if len({a.source_id for a in arts}) < (rule.min_sources or 1):
        return False
    if rule.keywords:
        words = [w.strip().lower() for w in rule.keywords.split(",") if w.strip()]
        text = " ".join(f"{a.title} {a.summary or ''}" for a in arts).lower()
        if not any(w in text for w in words):
            return False
    return True


def next_position() -> int:
    pos = [p.position for p in Pin.query.all()]
    return (max(pos) + 1) if pos else 1


def pin_story(story: Story, level: str = "important", user=None, rule: Rule | None = None, top: bool = False,
              auto_unpin: str = "idle12h", note: str | None = None) -> Pin:
    pin = Pin.query.filter_by(story_id=story.id).first()
    if not pin:
        pin = Pin(story_id=story.id, position=next_position())
        db.session.add(pin)
    pin.level = level or pin.level
    pin.pinned_by_id = getattr(user, "id", None) if user else pin.pinned_by_id
    pin.pinned_by_rule_id = rule.id if rule else pin.pinned_by_rule_id
    pin.pinned_at = now()
    pin.auto_unpin = auto_unpin
    if note:
        pin.note = note
    if top:
        for p in Pin.query.filter(Pin.id != pin.id).all():
            p.position += 1
        pin.position = 1
    story.level = max([story.level, level], key=lambda l: LEVELS.get(l, {}).get("rank", 0))
    db.session.flush()
    renumber_pins()
    return pin


def renumber_pins():
    pins = Pin.query.order_by(Pin.position.asc(), Pin.pinned_at.asc()).all()
    for i, p in enumerate(pins, start=1):
        p.position = i
    limit = max_pins()
    if limit <= 0:
        return                       # ไม่จำกัดจำนวนหมุด
    # เกินโควต้า → ปลดตัวท้ายที่มาจากกฎก่อน ตัวที่คนปักเองไม่แตะ
    while len(pins) > limit:
        victims = [p for p in reversed(pins) if p.pinned_by_rule_id]
        if not victims:
            break
        db.session.delete(victims[0])
        pins.remove(victims[0])


def apply_rules(new_article_ids: list[int]) -> list[str]:
    """เรียกหลัง fetch: ตรวจกฎกับ story ที่มีข่าวใหม่ คืนข้อความแจ้งเตือนที่ส่งไป"""
    rules = Rule.query.filter_by(enabled=True).all()
    if not rules or not new_article_ids:
        return []
    story_ids = {sid for (sid,) in db.session.query(Article.story_id).filter(Article.id.in_(new_article_ids)) if sid}
    notes = []
    for sid in story_ids:
        story = db.session.get(Story, sid)
        if not story:
            continue
        for rule in rules:
            if not _story_matches(rule, story):
                continue
            rule.hits = (rule.hits or 0) + 1
            if rule.action in ("pin", "pin_top"):
                existing = Pin.query.filter_by(story_id=story.id).first()
                if not existing:
                    pin_story(story, level=rule.set_level or "important", rule=rule, top=(rule.action == "pin_top"))
                    log.info("กฎ '%s' ปักหมุด: %s", rule.name, story.title[:80])
            elif rule.action == "flag":
                story.level = max([story.level, rule.set_level or "important"],
                                  key=lambda l: LEVELS.get(l, {}).get("rank", 0))
            if rule.notify_line:
                key = f"notified:{rule.id}:{story.id}"
                if not Setting.get(key):
                    cat = CATEGORIES.get(story.category, {}).get("label", "")
                    srcs = ", ".join(s.name for s in story.source_names(4))
                    first = story.articles.order_by(Article.published_at.asc()).first()
                    msg = f"[จับตา. · {cat}] กฎ: {rule.name}\n{story.title}\nแหล่ง: {srcs}\n{first.url if first else ''}"
                    if push_text(msg):
                        Setting.set(key, now().isoformat())
                        notes.append(msg)
    db.session.commit()
    return notes


def expire_pins():
    """ปลดหมุดตามเงื่อนไข auto_unpin"""
    for p in Pin.query.all():
        st = p.story
        last = st.last_seen_at if st else p.pinned_at
        mode = p.auto_unpin or "never"
        drop = False
        if mode == "idle12h":
            drop = (now() - last) > timedelta(hours=12)
        elif mode == "idle24h":
            drop = (now() - last) > timedelta(hours=24)
        elif mode == "tomorrow06":
            drop = bool(p.expires_at and now() >= p.expires_at)
        if drop:
            log.info("ปลดหมุดอัตโนมัติ (%s): %s", mode, st.title[:80] if st else p.id)
            db.session.delete(p)
    renumber_pins()
    db.session.commit()


def send_alerts(alert_ids: list[int]):
    """แจ้งเตือนทันทีจากแหล่งที่ตั้ง alert ไว้ (รวบเป็นข้อความเดียว)"""
    if not alert_ids:
        return
    alerts = Article.query.filter(Article.id.in_(alert_ids)).all()
    lines = []
    for a in alerts[:8]:
        lines.append(f"• {a.display_title[:90]}\n  ({a.source.name}) {a.url}")
    push_text("[จับตา. แจ้งเตือนทันที]\n" + "\n".join(lines))


def morning_brief_text() -> str:
    pins = Pin.query.order_by(Pin.position.asc()).all()
    since = now() - timedelta(hours=24)
    top = (Story.query.filter(Story.last_seen_at >= since).order_by(Story.score.desc()).limit(12).all())
    out = ["☀️ จับตา. สรุปเช้านี้"]
    if pins:
        out.append("\n📌 ปักหมุด")
        for p in pins:
            out.append(f"{p.position}. {p.story.title[:100]}")
    seen = {p.story_id for p in pins}
    for lvl in ("essential", "important", "should_know", "interesting"):
        items = [s for s in top if s.level == lvl and s.id not in seen][:3]
        if items:
            out.append(f"\n{LEVELS[lvl]['label']}")
            for s in items:
                out.append(f"– {s.title[:100]} ({s.source_count} แหล่ง)")
    return "\n".join(out)


def send_morning_brief():
    text = morning_brief_text()
    if push_text(text):
        log.info("ส่งสรุปเช้าเข้า LINE แล้ว")
    return text
