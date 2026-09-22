"""จับกลุ่มข่าวเรื่องเดียวกันจากหลายแหล่ง (ภาษาไทยไม่มีเว้นวรรค → ใช้ character n-gram Jaccard)"""
import re
from datetime import timedelta

from .models import db, Article, Story, now

_STRIP_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_PREFIX_RE = re.compile(r"^(ด่วน|ด่วน!|breaking|live|สด|คลิป|ชมคลิป|ภาพ|เปิด|เผย)[\s:!\-|]*", re.IGNORECASE)
# ตัดชื่อสำนักข่าวท้ายหัวข้อแบบ Google News ("... - ไทยรัฐ")
_SUFFIX_RE = re.compile(r"\s[-–|]\s[^-–|]{2,40}$")


def normalize(title: str) -> str:
    t = (title or "").strip()
    t = _SUFFIX_RE.sub("", t)
    t = _PREFIX_RE.sub("", t)
    t = _STRIP_RE.sub("", t.lower())
    return t


def shingles(text: str, n: int = 3) -> set:
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def similarity(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / float(len(sa | sb))


def containment(a: str, b: str) -> float:
    """สัดส่วน shingle ของหัวข้อสั้นที่อยู่ในหัวข้อยาว — ใช้จับ 'หัวข้อย่อ' กับ 'หัวข้อเต็ม'"""
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    return len(small & big) / float(len(small))


# น้ำหนักการจัดอันดับ — ปรับตรงนี้เพื่อเปลี่ยนว่าอะไรควรขึ้นบนสุด
W_WATCH = 10.0        # ตรงคำเฝ้าระวัง — สูงสุด เพราะผู้ใช้สั่งเองโดยตรง
W_SOCIAL = 6.0        # มีบัญชีบุคคล/เพจที่เฝ้าติดตามรายงาน
W_LOCAL_FIRST = 4.0   # ท้องถิ่นหรือบุคคลรายงานก่อนสื่อหลัก = สัญญาณเตือนล่วงหน้า
W_LEVEL = 2.0         # ระดับความสำคัญ (จำเป็น 4 ... น่าสนใจ 1)
DECAY_PER_HOUR = 0.5  # ความสดสำคัญมากกับงานเฝ้าระวัง จึงลดเร็วกว่าเดิมสามเท่า

SIM_THRESHOLD = 0.38
CONTAIN_THRESHOLD = 0.72
WINDOW_HOURS = 48


def assign_story(article: Article, candidates_cache: dict | None = None) -> Story:
    """หา story ที่ใกล้เคียงในช่วง 48 ชม. ถ้าไม่เจอสร้างใหม่"""
    norm = normalize(article.display_title)
    since = now() - timedelta(hours=WINDOW_HOURS)
    # ไม่จำกัดหมวด: ข่าวเรื่องเดียวกันอาจถูกจัดคนละหมวด (เช่น ชุมนุม vs ความเดือดร้อน)
    q = Story.query.filter(Story.last_seen_at >= since)
    best, best_score = None, 0.0
    for s in q.order_by(Story.last_seen_at.desc()).limit(600):
        n2 = normalize(s.title)
        sc = similarity(norm, n2)
        if sc < SIM_THRESHOLD and containment(norm, n2) >= CONTAIN_THRESHOLD and min(len(norm), len(n2)) >= 18:
            sc = CONTAIN_THRESHOLD
        if sc > best_score:
            best, best_score = s, sc
    if best and best_score >= SIM_THRESHOLD:
        story = best
    else:
        story = Story(title=article.display_title[:500], category=article.category, level=article.level,
                      first_seen_at=article.published_at or now(), last_seen_at=article.published_at or now())
        db.session.add(story)
        db.session.flush()
    article.story_id = story.id
    refresh_story(story)
    return story


LEVEL_RANK = {"essential": 4, "important": 3, "should_know": 2, "interesting": 1}


def refresh_story(story: Story):
    arts = story.articles.all()
    if not arts:
        return
    src_ids = {a.source_id for a in arts}
    story.source_count = len(src_ids)
    story.social_count = len({a.source_id for a in arts if a.source and a.source.source_type == "social"})
    times = [a.published_at or a.fetched_at for a in arts]
    story.first_seen_at = min(times)
    story.last_seen_at = max(times)
    # ระดับ = สูงสุดในกลุ่ม
    story.level = max(arts, key=lambda a: LEVEL_RANK.get(a.level, 0)).level
    if not story.category:
        cats = [a.category for a in arts if a.category]
        story.category = max(set(cats), key=cats.count) if cats else None
    # ใช้หัวข้อจากสื่อหลัก/รัฐเป็นชื่อกลุ่มถ้ามี
    pref = sorted(arts, key=lambda a: (0 if a.source and a.source.source_type in ("mainstream", "government") else 1,
                                       a.published_at or a.fetched_at))
    story.title = pref[0].display_title[:500]
    # สื่อท้องถิ่น/บุคคลรายงานก่อนสื่อหลัก ≥ 2 ชม. (หรือยังไม่มีสื่อหลักเลย)
    first = min(arts, key=lambda a: a.published_at or a.fetched_at)
    mains = [a for a in arts if a.source and a.source.source_type in ("mainstream", "foreign", "government")]
    if first.source and first.source.source_type in ("local", "social"):
        if not mains:
            story.local_first = True
        else:
            fm = min(mains, key=lambda a: a.published_at or a.fetched_at)
            story.local_first = ((fm.published_at or fm.fetched_at) - (first.published_at or first.fetched_at)) >= timedelta(hours=2)
    # คำเฝ้าระวังที่เจอในกลุ่มนี้ (รวมจากทุกข่าวในกลุ่ม ไม่นับซ้ำ)
    hits = sorted({w for a in arts for w in (a.watch_hits or "").split(",") if w.strip()})
    story.watch_hits = ",".join(hits)[:400] or None

    # คะแนนจัดอันดับตามตรรกะงานเฝ้าระวัง ไม่ใช่ตรรกะหนังสือพิมพ์
    #
    # เว็บนี้ไม่ได้ทำหน้าที่นำเสนอข่าว แต่เฝ้าระวังความเคลื่อนไหวของบุคคล/กลุ่ม
    # ที่ผู้ใช้ต้องการรู้ "จำนวนสำนักข่าวที่รายงาน" จึงไม่มีน้ำหนักในสูตรนี้เลย
    # เพราะมันวัดความดังของข่าว ไม่ได้วัดความสำคัญต่อการเฝ้าระวัง
    # ข่าวที่สื่อใหญ่สี่เจ้าลงพร้อมกันคือข่าวที่ทุกคนรู้แล้ว ไม่ใช่สิ่งที่ต้องเตือน
    # (ยังนับ source_count เก็บไว้แสดงผลว่า "รายงานตรงกันกี่แหล่ง" ตามเดิม)
    age_h = max(0.0, (now() - story.last_seen_at).total_seconds() / 3600.0)
    story.score = (
        (W_WATCH if hits else 0.0)                     # ตรงคำที่ผู้ใช้สั่งเฝ้าระวังเอง
        + (W_SOCIAL if story.social_count else 0.0)    # มาจากบัญชีบุคคล/เพจที่เฝ้าติดตาม
        + (W_LOCAL_FIRST if story.local_first else 0.0)  # ท้องถิ่นรายงานก่อนสื่อหลัก = เตือนล่วงหน้า
        + LEVEL_RANK.get(story.level, 1) * W_LEVEL
        - age_h * DECAY_PER_HOUR
    )
