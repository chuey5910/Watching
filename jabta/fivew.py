"""สกัด 5W1H จากหัวข้อและเนื้อข่าว

ทำด้วยกฎภาษา ไม่ได้ใช้โมเดลภาษา จึงต้องเข้าใจขอบเขต
- ใคร / ที่ไหน / เมื่อไหร่ จับได้ค่อนข้างแม่น เพราะข่าวไทยเขียนตามแบบแผน
  (คำนำหน้าชื่อ · "จังหวัด/อำเภอ X" · "เมื่อเวลา ... วันที่ ...")
- ทำไม / อย่างไร จับจากคำเชื่อมเหตุผล (เนื่องจาก เพราะ หลังจาก โดย)
  ได้เฉพาะกรณีที่ผู้เขียนใช้คำเหล่านี้ตรง ๆ ถ้าเล่าอ้อม ๆ จะจับไม่ได้
ช่องไหนจับไม่ได้จะไม่แสดง ดีกว่าเดาแล้วผิด
"""
import re

MONTHS = "(?:ม\\.ค\\.|ก\\.พ\\.|มี\\.ค\\.|เม\\.ย\\.|พ\\.ค\\.|มิ\\.ย\\.|ก\\.ค\\.|ส\\.ค\\.|ก\\.ย\\.|ต\\.ค\\.|พ\\.ย\\.|ธ\\.ค\\.|มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม)"

# สระหน้า เ แ โ ใ ไ อยู่นอกช่วง ก-ฮ ถ้าไม่ใส่เพิ่ม ชื่อและจังหวัดที่ขึ้นต้นด้วยสระเหล่านี้
# จะจับไม่ได้เลย (เชียงใหม่ แพร่ ระยอง ใจดี ไพบูลย์)
TH_START = "[ก-ฮเแโใไ]"

TITLE_PREFIX = r"(?:นาย|นางสาว|นาง|น\.ส\.|ดร\.|ส\.ส\.|ส\.ว\.|พล\.ต\.อ\.|พล\.ต\.ท\.|พล\.อ\.|พ\.ต\.อ\.|ผศ\.|รศ\.|ศ\.)"

PAT_WHO = re.compile(TITLE_PREFIX + r"\s?" + TH_START + r"[ก-๙]{1,14}(?:\s" + TH_START + r"[ก-๙]{1,18})?")
PAT_GROUP = re.compile(r"(?:กลุ่ม|เครือข่าย|สมาคม|ชมรม|สหภาพ|มูลนิธิ|สมัชชา|คณะ)[ก-๙]{2,24}")
PAT_CROWD = re.compile(r"(?:ชาวบ้าน|ประชาชน|เกษตรกร|ผู้ชุมนุม|นักศึกษา|แรงงาน)(?:จาก)?[ก-๙\s]{0,18}?(?:กว่า\s?)?\d[\d,]*\s?(?:คน|ราย|ครัวเรือน)")
PAT_WHERE = re.compile(r"(?:จังหวัด|จ\.|อำเภอ|อ\.|ตำบล|ต\.|เขต)\s?" + TH_START + r"[ก-๙]{1,20}")
PAT_WHEN = re.compile(r"(?:เมื่อ)?เวลา\s?[\d.:]{3,5}\s?น\.|วันที่\s?\d{1,2}\s?" + MONTHS + r"\s?\d{4}|\d{1,2}\s?" + MONTHS + r"\s?\d{2,4}")
PAT_WHY = re.compile(r"(?:เนื่องจาก|เพราะ(?:ว่า)?|สาเหตุ(?:มาจาก|เกิดจาก)?|หลัง(?!คา|งาน)|ส่งผลให้|จึง)(.{12,140})")
PAT_HOW = re.compile(r"(?:โดย(?:การ)?|ด้วยการ|ด้วยวิธี|ผ่านทาง)(.{12,140})")


def _trim_words(text: str, limit: int = 110) -> str:
    """ตัดให้จบที่ขอบเขตคำไทย ไม่ตัดกลางคำ"""
    text = re.sub(r"\s+", " ", text).strip(" .,·—-")
    if len(text) <= limit:
        return text
    try:
        from pythainlp.tokenize import word_tokenize
        out = ""
        for w in word_tokenize(text, engine="newmm"):
            if len(out) + len(w) > limit:
                break
            out += w
        return (out or text[:limit]).strip() + "…"
    except Exception:
        return text[:limit].strip() + "…"


def _first(pat, text, limit=110):
    m = pat.search(text or "")
    if not m:
        return None
    got = m.group(1) if m.groups() else m.group(0)
    got = _trim_words(got, limit)
    return got or None


def extract(title: str, body: str = "", published_at=None, region: str = None) -> dict:
    """คืนเฉพาะช่องที่จับได้จริง — ช่องที่จับไม่ได้จะไม่มีคีย์"""
    text = f"{title or ''}\n{body or ''}"
    head = (body or title or "")[:600]      # ย่อหน้าแรก ๆ มีข้อมูลหนาแน่นที่สุด

    out = {}
    who = _first(PAT_WHO, text, 60) or _first(PAT_CROWD, text, 60) or _first(PAT_GROUP, text, 60)
    if who:
        out["ใคร"] = who
    if title:
        out["ทำอะไร"] = _trim_words(title, 140)
    where = _first(PAT_WHERE, head, 40) or (region if region and region != "ทั่วประเทศ" else None)
    if where:
        out["ที่ไหน"] = where
    when = _first(PAT_WHEN, head, 40)
    if when:
        out["เมื่อไหร่"] = when
    elif published_at:
        out["เมื่อไหร่"] = published_at
    how = _first(PAT_HOW, body or "", 110)
    if how:
        out["อย่างไร"] = how
    why = _first(PAT_WHY, body or "", 110)
    if why:
        out["ทำไม"] = why
    return out


def missing(found: dict) -> list[str]:
    """ช่องที่ยังไม่มีข้อมูล — ใช้บอกผู้ใช้ว่าข่าวนี้ข้อมูลไม่ครบ"""
    return [k for k in ("ใคร", "ทำอะไร", "ที่ไหน", "เมื่อไหร่", "อย่างไร", "ทำไม") if k not in found]
