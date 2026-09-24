from datetime import datetime, timedelta
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ---------- ค่าคงที่ ----------
CATEGORIES = {
    "politics": {"label": "การเมือง", "color": "#F0A868"},
    "governance": {"label": "การปกครอง", "color": "#7FB7E6"},
    "hardship": {"label": "ความเดือดร้อนประชาชน", "color": "#8ED3A4"},
    "disaster": {"label": "ภัยพิบัติ", "color": "#E4572E"},
    "protest": {"label": "ชุมนุม / ประท้วง / คัดค้าน", "color": "#C08BF0"},
}
LEVELS = {
    "essential": {"label": "จำเป็น", "color": "#E4572E", "rank": 4},
    "important": {"label": "สำคัญ", "color": "#B8551E", "rank": 3},
    "should_know": {"label": "สมควรรู้", "color": "#2F6F8F", "rank": 2},
    "interesting": {"label": "น่าสนใจ", "color": "#3E8E5A", "rank": 1},
}
SOURCE_TYPES = {
    "mainstream": "สื่อหลักในประเทศ",
    "local": "สื่อท้องถิ่น",
    "foreign": "สื่อต่างประเทศ",
    "government": "หน่วยงานรัฐ",
    "social": "บัญชีบุคคล / โซเชียล",
}
FETCH_KINDS = {
    "rss": "RSS / Atom",
    "html": "อ่านจากหน้าเว็บ",
    "gnews": "Google News (site:)",
    "gnews_query": "Google News (คำค้น)",
    "telegram": "Telegram channel สาธารณะ",
    "youtube": "YouTube channel",
    "bluesky": "Bluesky",
    "rsshub": "RSSHub / RSS-Bridge (ติดตั้งเอง)",
}
USER_STATUS = {"pending": "รออนุมัติ", "approved": "อนุมัติแล้ว", "rejected": "ปฏิเสธ", "disabled": "ระงับ"}


def now():
    return datetime.utcnow()


# ---------- ผู้ใช้ ----------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(200))
    password_hash = db.Column(db.String(255))
    tailscale_login = db.Column(db.String(200), index=True)  # เช่น chuey@github  (จาก header)
    role = db.Column(db.String(16), default="member")  # admin | member
    status = db.Column(db.String(16), default="pending", index=True)
    note = db.Column(db.Text)  # เหตุผลที่สมัคร / หมายเหตุ admin
    created_at = db.Column(db.DateTime, default=now)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(64))
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    approved_by = db.relationship("User", remote_side=[id], foreign_keys=[approved_by_id])

    def set_password(self, pw: str):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, pw)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_approved(self):
        return self.status == "approved"

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > now())

    # Flask-Login: ผู้ใช้ที่ยังไม่อนุมัติถือว่า "ไม่ active" → login_required ปฏิเสธเอง
    @property
    def is_active(self):
        return self.status == "approved"


# ---------- แหล่งข่าว ----------
class Source(db.Model):
    __tablename__ = "sources"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    source_type = db.Column(db.String(16), nullable=False, index=True)  # SOURCE_TYPES
    fetch_kind = db.Column(db.String(16), nullable=False, default="rss")  # FETCH_KINDS
    homepage = db.Column(db.String(500))
    feed_url = db.Column(db.String(800))  # RSS url / gnews query / telegram channel / youtube id
    region = db.Column(db.String(80), default="ทั่วประเทศ")
    country = db.Column(db.String(80), default="ไทย")
    language = db.Column(db.String(8), default="th")
    # โซเชียล
    platform = db.Column(db.String(24))  # facebook, x, tiktok, youtube, telegram, bluesky
    handle = db.Column(db.String(160))
    group_name = db.Column(db.String(80))  # นักการเมือง / แกนนำ / นักข่าวพลเมือง / ผู้นำชุมชน
    # การคัดกรอง
    categories = db.Column(db.String(200), default="politics,governance,hardship,disaster,protest")
    keep_all = db.Column(db.Boolean, default=False)  # เก็บทุกข่าวโดยไม่กรองหมวด (เช่น บัญชีบุคคล)
    alert_categories = db.Column(db.String(200), default="")  # หมวดที่ให้แจ้งเตือนทันที
    alert_keywords = db.Column(db.String(400), default="")
    priority = db.Column(db.Integer, default=0)  # ค่าน้ำหนักเวลาจัดอันดับ
    enabled = db.Column(db.Boolean, default=True, index=True)
    # สถานะการดึง
    last_fetched_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    last_status = db.Column(db.String(24), default="new")  # ok | error | empty | new
    last_error = db.Column(db.Text)
    consecutive_errors = db.Column(db.Integer, default=0)
    resolved_feed_url = db.Column(db.String(800))  # url ที่ค้นพบอัตโนมัติ (auto-discovery / fallback)
    etag = db.Column(db.String(200))
    modified = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    articles = db.relationship("Article", backref="source", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def type_label(self):
        return SOURCE_TYPES.get(self.source_type, self.source_type)

    @property
    def category_list(self):
        return [c for c in (self.categories or "").split(",") if c]

    def today_count(self):
        since = now() - timedelta(hours=24)
        return self.articles.filter(Article.fetched_at >= since).count()


# ---------- ข่าว ----------
class Story(db.Model):
    """กลุ่มข่าวเรื่องเดียวกันจากหลายแหล่ง"""
    __tablename__ = "stories"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500))
    category = db.Column(db.String(16), index=True)
    level = db.Column(db.String(16), default="interesting", index=True)
    first_seen_at = db.Column(db.DateTime, default=now, index=True)
    last_seen_at = db.Column(db.DateTime, default=now, index=True)
    source_count = db.Column(db.Integer, default=1)
    social_count = db.Column(db.Integer, default=0)
    local_first = db.Column(db.Boolean, default=False)
    # คำเฝ้าระวังที่เจอในข่าวของกลุ่มนี้ คั่น , — ใช้ทั้งจัดอันดับและแสดงเหตุผลบนกระดาน
    watch_hits = db.Column(db.String(400))  # สื่อท้องถิ่น/บุคคลรายงานก่อนสื่อหลัก
    score = db.Column(db.Float, default=0.0)

    articles = db.relationship("Article", backref="story", lazy="dynamic")

    def source_names(self, limit=6):
        seen, out = set(), []
        for a in self.articles.order_by(Article.published_at.asc()):
            if a.source_id in seen:
                continue
            seen.add(a.source_id)
            out.append(a.source)
            if len(out) >= limit:
                break
        return out


class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id"), nullable=False, index=True)
    story_id = db.Column(db.Integer, db.ForeignKey("stories.id"), index=True)
    guid = db.Column(db.String(600), index=True)
    url = db.Column(db.String(1000), nullable=False)
    url_hash = db.Column(db.String(40), unique=True, index=True)
    title = db.Column(db.String(600), nullable=False)
    title_th = db.Column(db.String(600))  # หัวข้อแปลไทย (ถ้ามี)
    summary = db.Column(db.Text)
    image_url = db.Column(db.String(1000))
    author = db.Column(db.String(200))
    published_at = db.Column(db.DateTime, index=True)
    fetched_at = db.Column(db.DateTime, default=now, index=True)
    category = db.Column(db.String(16), index=True)
    categories = db.Column(db.String(120))  # ทุกหมวดที่เข้าเกณฑ์ คั่น ,
    level = db.Column(db.String(16), default="interesting")
    matched_keywords = db.Column(db.String(400))
    region = db.Column(db.String(80))
    is_alert = db.Column(db.Boolean, default=False)  # เข้าเงื่อนไขแจ้งเตือน
    # คำเฝ้าระวังที่เจอในหัวข้อหรือเนื้อข่าว คั่น , — ข่าวที่มีค่านี้จะไม่ถูกกรองทิ้ง
    # แม้ไม่เข้า 5 หมวด เพราะผู้ใช้สั่งเฝ้าระวังคำนั้นไว้เอง
    watch_hits = db.Column(db.String(400))
    # เนื้อข่าวย่อหน้าต้น ๆ ที่ดึงจากหน้าเว็บต้นทาง — RSS ให้สรุปมาแค่ 50-60 ตัวอักษร
    # ซึ่งไม่พอจะรู้ว่าใครทำอะไรที่ไหน ต้องไปอ่านหน้าจริงถึงจะได้ 5W1H
    body = db.Column(db.Text)
    body_fetched_at = db.Column(db.DateTime)
    hidden = db.Column(db.Boolean, default=False)

    @property
    def display_title(self):
        return self.title_th or self.title

    @property
    def category_list(self):
        return [c for c in (self.categories or "").split(",") if c]


# ---------- ปักหมุด ----------
class Pin(db.Model):
    __tablename__ = "pins"
    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey("stories.id"), nullable=False, unique=True)
    position = db.Column(db.Integer, default=1, index=True)
    level = db.Column(db.String(16), default="important")
    note = db.Column(db.String(300))  # คำอธิบายที่ผู้ใช้เขียนเอง
    pinned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    pinned_by_rule_id = db.Column(db.Integer, db.ForeignKey("rules.id"))
    pinned_at = db.Column(db.DateTime, default=now)
    auto_unpin = db.Column(db.String(24), default="idle12h")  # idle12h | idle24h | tomorrow06 | never
    expires_at = db.Column(db.DateTime)

    story = db.relationship("Story", backref=db.backref("pin", uselist=False))
    pinned_by = db.relationship("User", foreign_keys=[pinned_by_id])
    rule = db.relationship("Rule", foreign_keys=[pinned_by_rule_id])


class Rule(db.Model):
    """กฎปักหมุด/แจ้งเตือนอัตโนมัติ"""
    __tablename__ = "rules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    enabled = db.Column(db.Boolean, default=True)
    category = db.Column(db.String(16))  # ว่าง = ทุกหมวด
    min_sources = db.Column(db.Integer, default=1)
    within_hours = db.Column(db.Integer, default=24)
    keywords = db.Column(db.String(500))  # คั่น , — เจอคำใดคำหนึ่ง
    source_type = db.Column(db.String(16))  # จำกัดประเภทแหล่ง (เช่น government / social)
    source_group = db.Column(db.String(80))  # จำกัดกลุ่มบัญชีบุคคล
    action = db.Column(db.String(16), default="pin")  # pin | pin_top | flag | alert
    set_level = db.Column(db.String(16), default="essential")
    notify_line = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now)
    hits = db.Column(db.Integer, default=0)


class Keyword(db.Model):
    """คำสำคัญสำหรับจัดหมวด (system) และคำที่ผู้ใช้ติดตามพิเศษ (watch)"""
    __tablename__ = "keywords"
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(120), nullable=False, index=True)
    category = db.Column(db.String(16))  # ใช้กับ kind=classify
    kind = db.Column(db.String(16), default="watch")  # classify | watch | level_essential | level_important
    weight = db.Column(db.Integer, default=1)
    enabled = db.Column(db.Boolean, default=True)


# ---------- Log ----------
class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, default=now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    username = db.Column(db.String(64))
    action = db.Column(db.String(48), index=True)  # login_ok, login_fail, register, approve, pin, ...
    target = db.Column(db.String(200))
    detail = db.Column(db.Text)
    ip = db.Column(db.String(64))
    tailscale_login = db.Column(db.String(200))
    user_agent = db.Column(db.String(300))
    ok = db.Column(db.Boolean, default=True)

    user = db.relationship("User", foreign_keys=[user_id])


class FetchLog(db.Model):
    __tablename__ = "fetch_logs"
    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, default=now, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id"), index=True)
    status = db.Column(db.String(24))
    new_items = db.Column(db.Integer, default=0)
    kept_items = db.Column(db.Integer, default=0)
    duration_ms = db.Column(db.Integer)
    message = db.Column(db.Text)

    source = db.relationship("Source")


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)

    @staticmethod
    def get(key, default=None):
        s = db.session.get(Setting, key)
        return s.value if s else default

    @staticmethod
    def set(key, value):
        s = db.session.get(Setting, key)
        if not s:
            s = Setting(key=key)
            db.session.add(s)
        s.value = value
