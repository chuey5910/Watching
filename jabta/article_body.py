"""ดึงเนื้อข่าวจากหน้าเว็บต้นทาง

RSS ให้สรุปมาสั้นมาก (วัดจากข่าวจริงได้ 50-60 ตัวอักษร) และมักถูกตัดกลางคัน
ซึ่งไม่พอจะรู้ว่าใครทำอะไรที่ไหนเมื่อไหร่ จึงต้องไปอ่านหน้าจริง
เก็บเฉพาะย่อหน้าต้น ๆ เพราะข่าวไทยมักสรุป 5W1H ไว้ในย่อหน้าแรก ๆ
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup
from flask import current_app

log = logging.getLogger("jabta.body")

MAX_CHARS = 1500

# แท็กที่ไม่ใช่เนื้อข่าว ตัดทิ้งก่อนอ่าน
DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form",
             "iframe", "noscript", "figure", "figcaption"]

# คลาส/ไอดีที่มักเป็นส่วนประกอบรอบข้าง ไม่ใช่เนื้อข่าว
DROP_HINTS = re.compile(r"(related|recommend|sidebar|comment|share|social|advert|banner|menu|breadcrumb|tag|popular|footer|header)", re.I)

# จุดที่มักเป็นท้ายบทความ ตัดตั้งแต่ตรงนี้
CUT_MARKERS = ["อ่านข่าวที่เกี่ยวข้อง", "ข่าวที่เกี่ยวข้อง", "อ่านเพิ่มเติม", "ติดตามข่าวสาร",
               "แท็กที่เกี่ยวข้อง", "The post", "appeared first on", "Related stories"]


def _pick_container(soup):
    """เลือกก้อนที่น่าจะเป็นเนื้อข่าวที่สุด — นับจำนวนตัวอักษรใน <p>"""
    best, best_len = None, 0
    for el in soup.find_all(["article", "main", "div", "section"]):
        cls = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        if DROP_HINTS.search(cls):
            continue
        n = sum(len(p.get_text(strip=True)) for p in el.find_all("p", recursive=False)) or \
            sum(len(p.get_text(strip=True)) for p in el.find_all("p"))
        if n > best_len:
            best, best_len = el, n
    return best or soup


def extract_body(html: "str | bytes") -> str:
    # ส่ง bytes ให้ parser เดา encoding เอง — requests เดาเป็น ISO-8859-1
    # เมื่อ header ไม่ระบุ charset (ตาม RFC) ซึ่งทำให้ภาษาไทยเพี้ยนทั้งหน้า
    soup = BeautifulSoup(html, "lxml")
    for t in soup(DROP_TAGS):
        t.decompose()
    for el in soup.find_all(attrs={"class": DROP_HINTS}):
        el.decompose()
    container = _pick_container(soup)
    parts = []
    for p in container.find_all("p"):
        txt = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        # ต้องเช็กจุดตัดก่อนกรองความยาว เพราะหัวข้อ "อ่านข่าวที่เกี่ยวข้อง"
        # มักสั้นกว่าเกณฑ์ ถ้าข้ามไปก่อนจะพาข่าวแนะนำใต้มันติดมาด้วย
        if parts and any(mark in txt for mark in CUT_MARKERS):
            break
        if len(txt) < 30:          # ข้ามบรรทัดสั้น ๆ ที่มักเป็นเครดิตภาพหรือป้ายกำกับ
            continue
        parts.append(txt)
        if sum(len(x) for x in parts) >= MAX_CHARS:
            break
    text = "\n".join(parts)
    for mark in CUT_MARKERS:
        idx = text.find(mark)
        if idx > 200:
            text = text[:idx]
    return text.strip()[:MAX_CHARS]


def fetch_bodies(article_ids: list[int]) -> int:
    """ดึงเนื้อข่าวให้ข่าวที่ระบุ คืนจำนวนที่สำเร็จ — เรียกหลังเก็บข่าวเสร็จ"""
    from .models import db, Article, now
    from .fetcher import _session

    if not article_ids:
        return 0
    arts = Article.query.filter(Article.id.in_(article_ids), Article.body.is_(None)).all()
    if not arts:
        return 0
    sess = _session()
    timeout = current_app.config.get("FETCH_TIMEOUT", 20)

    def one(url):
        try:
            r = sess.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code != 200 or "html" not in (r.headers.get("Content-Type") or ""):
                return None
            return extract_body(r.content)
        except Exception as ex:
            log.debug("ดึงเนื้อข่าวไม่ได้ %s: %s", url[:60], ex)
            return None

    workers = min(6, max(1, len(arts)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bodies = list(pool.map(one, [a.url for a in arts]))
    ok = 0
    for a, body in zip(arts, bodies):
        a.body_fetched_at = now()
        if body and len(body) > len(a.summary or ""):
            a.body = body
            ok += 1
    db.session.commit()
    log.info("ดึงเนื้อข่าวสำเร็จ %d จาก %d", ok, len(arts))
    return ok
