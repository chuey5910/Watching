"""ค่าตั้งค่าของระบบ จับตา. — อ่านจาก environment variable (ไฟล์ .env) เป็นหลัก"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please-" + os.urandom(8).hex())
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'jabta.sqlite3'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Tailscale serve ทำ HTTPS ให้ — ถ้าเข้าผ่าน https ให้ตั้ง SESSION_COOKIE_SECURE=1
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_HOURS", "72")) * 3600

    # ---------- Tailscale ----------
    # อนุญาตเฉพาะ IP ในช่วง Tailnet (100.64.0.0/10) + loopback  (ปิดได้เมื่อทดสอบในเครื่อง)
    TAILSCALE_ONLY = _bool("TAILSCALE_ONLY", True)
    # เชื่อ header Tailscale-User-Login ที่ `tailscale serve` ใส่มาให้ (มาจาก loopback เท่านั้น)
    TRUST_TAILSCALE_HEADERS = _bool("TRUST_TAILSCALE_HEADERS", True)
    # CIDR ที่ถือว่าเชื่อถือได้เพิ่มเติม (คั่นด้วย ,) เช่น LAN ที่บ้าน
    EXTRA_TRUSTED_CIDRS = [c.strip() for c in os.environ.get("EXTRA_TRUSTED_CIDRS", "").split(",") if c.strip()]

    # ---------- การสมัคร/อนุมัติ ----------
    REGISTRATION_OPEN = _bool("REGISTRATION_OPEN", True)
    # ผู้ใช้คนแรกที่สมัครจะเป็น admin และอนุมัติอัตโนมัติ
    FIRST_USER_IS_ADMIN = _bool("FIRST_USER_IS_ADMIN", True)
    MAX_LOGIN_FAILS = int(os.environ.get("MAX_LOGIN_FAILS", "8"))
    LOCKOUT_MINUTES = int(os.environ.get("LOCKOUT_MINUTES", "15"))

    # ---------- ดึงข่าว ----------
    FETCH_INTERVAL_MINUTES = int(os.environ.get("FETCH_INTERVAL_MINUTES", "10"))
    FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "20"))
    FETCH_WORKERS = int(os.environ.get("FETCH_WORKERS", "8"))
    USER_AGENT = os.environ.get("USER_AGENT", "Mozilla/5.0 (compatible; JabtaNewsBoard/1.0; +local)")
    ARTICLE_RETENTION_DAYS = int(os.environ.get("ARTICLE_RETENTION_DAYS", "45"))
    # ดึงเฉพาะข่าวที่เข้าหมวดที่สนใจ (การเมือง/การปกครอง/ความเดือดร้อน/ภัยพิบัติ/ชุมนุม) เท่านั้น
    KEEP_ONLY_MATCHED = _bool("KEEP_ONLY_MATCHED", True)
    # ถ้าใช้ RSSHub / RSS-Bridge ที่ติดตั้งเองสำหรับ Facebook/X/TikTok ใส่ base URL ที่นี่
    RSSHUB_BASE = os.environ.get("RSSHUB_BASE", "").rstrip("/")
    RSSBRIDGE_BASE = os.environ.get("RSSBRIDGE_BASE", "").rstrip("/")

    # ---------- LINE (สรุปเช้า / แจ้งเตือน) ----------
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    LINE_TO = os.environ.get("LINE_TO", "")  # userId / groupId ปลายทาง
    MORNING_BRIEF_TIME = os.environ.get("MORNING_BRIEF_TIME", "06:30")

    # ---------- Log ----------
    LOG_DIR = Path(os.environ.get("LOG_DIR", BASE_DIR / "logs"))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    TIMEZONE = os.environ.get("TZ", "Asia/Bangkok")
