"""ดึงข่าวจากทุกแหล่ง: RSS/Atom, หน้าเว็บ, Google News, Telegram, YouTube, Bluesky, RSSHub
มี auto-discovery และ fallback ไป Google News (site:โดเมน) เมื่อ RSS ใช้ไม่ได้"""
import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, quote_plus, urlencode

import feedparser
import requests
from bs4 import BeautifulSoup
from flask import current_app

from .models import db, Source, Article, FetchLog, now
from .classifier import classify
from .cluster import assign_story

log = logging.getLogger("jabta.fetch")

COMMON_FEED_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/atom.xml", "/rss/news.xml", "/?feed=rss2", "/index.xml"]
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "ref", "source", "_ga")


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": current_app.config["USER_AGENT"], "Accept-Language": "th,en;q=0.8"})
    return s


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        qs = "&".join(kv for kv in p.query.split("&") if kv and not kv.lower().startswith(TRACKING_PARAMS))
        path = p.path.rstrip("/") or "/"
        return f"{p.scheme or 'https'}://{p.netloc.lower()}{path}" + (f"?{qs}" if qs else "")
    except Exception:
        return url


def url_hash(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()


def gnews_url(query: str, lang: str = "th") -> str:
    if lang == "en":
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    else:
        params = {"q": query, "hl": "th", "gl": "TH", "ceid": "TH:th"}
    return "https://news.google.com/rss/search?" + urlencode(params)


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ---------- ตัวแปลง entry → dict กลาง ----------
def _entry_time(e) -> datetime | None:
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        t = e.get(k)
        if t:
            try:
                return datetime(*t[:6])
            except Exception:
                pass
    return None


def _clean_html(s: str, limit: int = 600) -> str:
    if not s:
        return ""
    txt = BeautifulSoup(s, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", txt)[:limit]


def _entry_image(e) -> str | None:
    for m in e.get("media_content", []) or []:
        if m.get("url") and ("image" in (m.get("medium") or "image") or m.get("type", "").startswith("image")):
            return m["url"]
    for m in e.get("media_thumbnail", []) or []:
        if m.get("url"):
            return m["url"]
    for l in e.get("links", []) or []:
        if l.get("rel") == "enclosure" and str(l.get("type", "")).startswith("image"):
            return l.get("href")
    html = (e.get("summary") or "") + "".join(c.get("value", "") for c in e.get("content", []) or [])
    m = re.search(r'<img[^>]+src="([^"]+)"', html)
    return m.group(1) if m else None


def parse_feed(content: bytes | str, base_url: str, strip_gnews_suffix: bool = False) -> list[dict]:
    fp = feedparser.parse(content)
    items = []
    for e in fp.entries:
        link = e.get("link") or ""
        title = (e.get("title") or "").strip()
        if not link or not title:
            continue
        if strip_gnews_suffix:
            title = re.sub(r"\s[-–]\s[^-–]{2,60}$", "", title).strip()
        summary = _clean_html(e.get("summary") or (e.get("content") or [{}])[0].get("value", ""))
        items.append({
            "guid": (e.get("id") or link)[:600],
            "url": urljoin(base_url, link),
            "title": title[:600],
            "summary": summary,
            "image": _entry_image(e),
            "author": (e.get("author") or "")[:200] or None,
            "published": _entry_time(e),
        })
    return items


# ---------- ตัวดึงแต่ละชนิด ----------
def fetch_rss(src: Source, s: requests.Session, url: str) -> list[dict]:
    headers = {}
    if src.etag:
        headers["If-None-Match"] = src.etag
    if src.modified:
        headers["If-Modified-Since"] = src.modified
    r = s.get(url, timeout=current_app.config["FETCH_TIMEOUT"], headers=headers, allow_redirects=True)
    if r.status_code == 304:
        return []
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    body = r.content
    if b"<rss" not in body[:4000] and b"<feed" not in body[:4000] and b"<rdf" not in body[:4000] and "xml" not in ctype:
        raise ValueError("ไม่ใช่ RSS/Atom")
    src.etag = r.headers.get("ETag")
    src.modified = r.headers.get("Last-Modified")
    return parse_feed(body, url, strip_gnews_suffix="news.google.com" in url)


def discover_feed(src: Source, s: requests.Session) -> str | None:
    """หา RSS จากหน้าแรก: <link rel=alternate> แล้วลอง path ยอดนิยม"""
    if not src.homepage:
        return None
    try:
        r = s.get(src.homepage, timeout=current_app.config["FETCH_TIMEOUT"])
        soup = BeautifulSoup(r.text, "lxml")
        for l in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            t = (l.get("type") or "").lower()
            if "rss" in t or "atom" in t or "xml" in t:
                href = l.get("href")
                if href:
                    return urljoin(src.homepage, href)
    except Exception as ex:
        log.debug("discover homepage fail %s: %s", src.name, ex)
    for p in COMMON_FEED_PATHS:
        cand = urljoin(src.homepage, p)
        try:
            r = s.get(cand, timeout=10)
            if r.ok and (b"<rss" in r.content[:4000] or b"<feed" in r.content[:4000]):
                return cand
        except Exception:
            continue
    return None


def fetch_html(src: Source, s: requests.Session) -> list[dict]:
    """อ่านหัวข้อข่าวจากหน้าเว็บทั่วไป: เก็บลิงก์ในโดเมนเดียวกันที่มีข้อความยาวพอเป็นหัวข้อข่าว"""
    url = src.feed_url or src.homepage
    r = s.get(url, timeout=current_app.config["FETCH_TIMEOUT"])
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    dom = domain_of(url)
    seen, items = set(), []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) < 22 or len(text) > 220:
            continue
        href = urljoin(url, a["href"])
        if domain_of(href) != dom or href in seen:
            continue
        path = urlparse(href).path
        if path in ("", "/") or path.count("/") < 1 or any(x in href for x in ("/tag/", "/category/", "/author/", "#", "javascript:")):
            continue
        seen.add(href)
        items.append({"guid": href, "url": href, "title": text, "summary": "", "image": None, "author": None, "published": None})
    return items[:80]


def fetch_telegram(src: Source, s: requests.Session) -> list[dict]:
    ch = (src.handle or src.feed_url or "").strip().lstrip("@").replace("https://t.me/s/", "").replace("https://t.me/", "").strip("/")
    url = src.feed_url if (src.feed_url or "").startswith("http") and "t.me" not in (src.feed_url or "") else f"https://t.me/s/{ch}"
    r = s.get(url, timeout=current_app.config["FETCH_TIMEOUT"])
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    items = []
    for msg in soup.select(".tgme_widget_message"):
        post = msg.get("data-post")
        text_el = msg.select_one(".tgme_widget_message_text")
        if not post or not text_el:
            continue
        text = text_el.get_text(" ", strip=True)
        if len(text) < 10:
            continue
        t_el = msg.select_one("time[datetime]")
        published = None
        if t_el:
            try:
                published = datetime.fromisoformat(t_el["datetime"].replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
        img = None
        ph = msg.select_one(".tgme_widget_message_photo_wrap")
        if ph and "background-image" in (ph.get("style") or ""):
            m = re.search(r"url\('([^']+)'\)", ph["style"])
            img = m.group(1) if m else None
        items.append({"guid": post, "url": f"https://t.me/{post}", "title": text[:160], "summary": text[:600],
                      "image": img, "author": ch, "published": published})
    return items


def resolve_fetch_url(src: Source) -> tuple[str | None, str]:
    """คืน (url ที่จะดึงแบบ RSS, kind ที่ใช้จริง)"""
    k = src.fetch_kind
    if k == "rss":
        return (src.resolved_feed_url or src.feed_url), "rss"
    if k == "gnews":
        dom = (src.feed_url or domain_of(src.homepage or "")).replace("https://", "").replace("http://", "").strip("/")
        return gnews_url(f"site:{dom}", src.language or "th"), "gnews"
    if k == "gnews_query":
        return gnews_url(src.feed_url or src.name, src.language or "th"), "gnews_query"
    if k == "youtube":
        cid = (src.feed_url or src.handle or "").strip()
        if cid.startswith("http"):
            return cid, "youtube"
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", "youtube"
    if k == "bluesky":
        h = (src.handle or src.feed_url or "").strip().lstrip("@")
        return f"https://bsky.app/profile/{h}/rss", "bluesky"
    if k == "rsshub":
        u = (src.feed_url or "").strip()
        if u.startswith("/"):
            base = current_app.config.get("RSSHUB_BASE") or ""
            if not base:
                return None, "rsshub"
            u = base + u
        return u, "rsshub"
    return None, k


def fetch_source(src: Source) -> dict:
    """ดึงหนึ่งแหล่ง คืน dict สรุป (ยังไม่ commit — ให้ run_fetch จัดการ)"""
    t0 = time.time()
    s = _session()
    result = {"source_id": src.id, "status": "ok", "items": [], "message": ""}
    try:
        kind = src.fetch_kind
        if kind == "html":
            result["items"] = fetch_html(src, s)
        elif kind == "telegram":
            result["items"] = fetch_telegram(src, s)
        else:
            url, real_kind = resolve_fetch_url(src)
            if not url and real_kind == "rss":
                # ไม่ได้ระบุ RSS → ค้นหาจากหน้าแรกก่อน ไม่เจอค่อยใช้ Google News
                url = discover_feed(src, s)
                if url:
                    src.resolved_feed_url = url
                    result["message"] = f"ใช้ฟีดที่ค้นพบอัตโนมัติ: {url}"
                else:
                    dom = domain_of(src.homepage or "")
                    if not dom:
                        raise ValueError("ไม่มีลิงก์ที่ดึงได้ (ใส่ RSS หรือหน้าแรกของเว็บ)")
                    url = gnews_url(f"site:{dom}", src.language or "th")
                    src.resolved_feed_url = url
                    result["message"] = f"ไม่พบ RSS → ใช้ Google News site:{dom}"
            if not url:
                raise ValueError("ไม่มี URL ที่ดึงได้ (ตรวจ RSSHUB_BASE หรือ feed_url)")
            try:
                result["items"] = fetch_rss(src, s, url)
            except Exception as ex1:
                if real_kind != "rss":
                    raise
                # RSS พัง → ลอง auto-discovery → fallback Google News site:
                found = discover_feed(src, s)
                if found and found != url:
                    result["items"] = fetch_rss(src, s, found)
                    src.resolved_feed_url = found
                    result["message"] = f"ใช้ฟีดที่ค้นพบอัตโนมัติ: {found}"
                else:
                    dom = domain_of(src.homepage or src.feed_url or "")
                    if not dom:
                        raise ex1
                    gu = gnews_url(f"site:{dom}", src.language or "th")
                    try:
                        result["items"] = fetch_rss(src, s, gu)
                    except Exception as ex2:
                        raise RuntimeError(f"RSS: {type(ex1).__name__} {str(ex1)[:120]} | Google News fallback: "
                                           f"{type(ex2).__name__} {str(ex2)[:120]}") from ex2
                    src.resolved_feed_url = gu
                    result["message"] = f"RSS ใช้ไม่ได้ ({type(ex1).__name__}) → ใช้ Google News site:{dom}"
        if not result["items"]:
            result["status"] = "empty"
    except Exception as ex:
        result["status"] = "error"
        result["message"] = f"{type(ex).__name__}: {str(ex)[:300]}"
    result["duration_ms"] = int((time.time() - t0) * 1000)
    return result


# ---------- บันทึกลง DB ----------
def store_items(src: Source, items: list[dict]) -> tuple[int, int, list[Article]]:
    """คืน (จำนวนใหม่ทั้งหมด, จำนวนที่เก็บหลังกรอง, รายการ Article ที่เก็บ)"""
    keep_only = current_app.config["KEEP_ONLY_MATCHED"] and not src.keep_all
    allowed = set(src.category_list)
    new_total, kept = 0, []
    horizon = now() - timedelta(days=current_app.config["ARTICLE_RETENTION_DAYS"])
    for it in items:
        h = url_hash(it["url"])
        if db.session.query(Article.id).filter_by(url_hash=h).first():
            continue
        new_total += 1
        if it["published"] and it["published"] < horizon:
            continue
        c = classify(it["title"], it["summary"])
        cats = [x for x in c["categories"] if (not allowed or x in allowed)]
        if keep_only and not cats:
            continue
        art = Article(
            source_id=src.id, guid=it["guid"], url=it["url"][:1000], url_hash=h, title=it["title"][:600],
            summary=it["summary"], image_url=(it["image"] or "")[:1000] or None, author=it["author"],
            published_at=it["published"] or now(), category=(cats[0] if cats else c["primary"]),
            categories=",".join(cats or c["categories"]), level=c["level"], matched_keywords=",".join(c["matched"])[:400],
            region=src.region,
        )
        # แจ้งเตือน: หมวด/คำสำคัญของแหล่งนี้
        alert_cats = set(x for x in (src.alert_categories or "").split(",") if x)
        alert_words = [w.strip().lower() for w in (src.alert_keywords or "").split(",") if w.strip()]
        text_l = f"{art.title} {art.summary or ''}".lower()
        if (alert_cats & set(art.category_list)) or any(w in text_l for w in alert_words):
            art.is_alert = True
        db.session.add(art)
        db.session.flush()
        assign_story(art)
        kept.append(art)
    return new_total, len(kept), kept


def run_fetch(source_ids: list[int] | None = None, app=None) -> dict:
    """ดึงทุกแหล่งที่เปิดใช้ (ขนานกัน) แล้วบันทึก — เรียกจาก scheduler / CLI / ปุ่มในเว็บ"""
    app = app or current_app._get_current_object()
    summary = {"sources": 0, "ok": 0, "error": 0, "new": 0, "kept": 0, "alert_ids": [], "kept_ids": []}
    with app.app_context():
        q = Source.query.filter_by(enabled=True)
        if source_ids:
            q = q.filter(Source.id.in_(source_ids))
        sources = q.all()
        summary["sources"] = len(sources)
        results = []
        with ThreadPoolExecutor(max_workers=app.config["FETCH_WORKERS"]) as ex:
            futs = {}
            for src in sources:
                # แต่ละ thread ต้องมี app context ของตัวเอง
                def job(sid=src.id):
                    with app.app_context():
                        s = db.session.get(Source, sid)
                        r = fetch_source(s)
                        r["etag"], r["modified"], r["resolved"] = s.etag, s.modified, s.resolved_feed_url
                        db.session.rollback()  # ไม่ commit จาก thread
                        return r
                futs[ex.submit(job)] = src.id
            for f in as_completed(futs):
                try:
                    results.append(f.result())
                except Exception as e:  # pragma: no cover
                    results.append({"source_id": futs[f], "status": "error", "items": [], "message": repr(e), "duration_ms": 0})
        for r in results:
            src = db.session.get(Source, r["source_id"])
            if not src:
                continue
            src.last_fetched_at = now()
            src.last_status = r["status"]
            src.etag, src.modified = r.get("etag"), r.get("modified")
            if r.get("resolved"):
                src.resolved_feed_url = r["resolved"]
            new_n, kept_n = 0, 0
            if r["status"] in ("ok", "empty"):
                src.last_success_at = now()
                src.consecutive_errors = 0
                src.last_error = None
                try:
                    new_n, kept_n, arts = store_items(src, r["items"])
                    summary["kept_ids"].extend(a.id for a in arts)
                    summary["alert_ids"].extend(a.id for a in arts if a.is_alert)
                    summary["ok"] += 1
                except Exception as ex:
                    db.session.rollback()
                    src = db.session.get(Source, r["source_id"])
                    src.last_status, src.last_error = "error", f"store: {ex!r}"[:500]
                    summary["error"] += 1
                    log.exception("store fail %s", src.name)
            else:
                src.consecutive_errors = (src.consecutive_errors or 0) + 1
                src.last_error = r["message"][:500]
                summary["error"] += 1
                log.warning("ดึงไม่ได้ [%s] %s", src.name, r["message"])
            summary["new"] += new_n
            summary["kept"] += kept_n
            db.session.add(FetchLog(source_id=src.id, status=src.last_status, new_items=new_n, kept_items=kept_n,
                                    duration_ms=r.get("duration_ms"), message=(r.get("message") or "")[:1000]))
            db.session.commit()
        log.info("fetch เสร็จ: %d แหล่ง ok=%d error=%d ใหม่=%d เก็บ=%d", summary["sources"], summary["ok"],
                 summary["error"], summary["new"], summary["kept"])
        # ล้างข่าวเก่า
        horizon = now() - timedelta(days=app.config["ARTICLE_RETENTION_DAYS"])
        Article.query.filter(Article.fetched_at < horizon).delete(synchronize_session=False)
        db.session.commit()
    return summary
