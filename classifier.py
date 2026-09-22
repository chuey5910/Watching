"""จัดหมวดข่าวด้วยคำสำคัญ (ไทย/อังกฤษ) + ประเมินระดับ จำเป็น/สำคัญ/สมควรรู้/น่าสนใจ
คำสำคัญเริ่มต้นอยู่ที่นี่ และผู้ดูแลเพิ่ม/ปิดได้ผ่านตาราง keywords (kind=classify)"""
import re
from functools import lru_cache

from .models import db, Keyword

DEFAULT_KEYWORDS = {
    "politics": [
        "การเมือง", "รัฐบาล", "นายกรัฐมนตรี", "นายกฯ", "ครม.", "คณะรัฐมนตรี", "รัฐมนตรี", "สภา", "ส.ส.", "สส.", "ส.ว.", "สว.",
        "วุฒิสภา", "ฝ่ายค้าน", "พรรค", "อภิปราย", "ไม่ไว้วางใจ", "ญัตติ", "เลือกตั้ง", "กกต.", "ยุบสภา", "รัฐธรรมนูญ",
        "ศาลรัฐธรรมนูญ", "ป.ป.ช.", "นิรโทษกรรม", "ประชามติ", "แก้รัฐธรรมนูญ", "รัฐประหาร", "ทหาร", "กองทัพ", "ผบ.ทบ.",
        "โหวต", "งบประมาณ", "ร่าง พ.ร.บ.", "พ.ร.ก.", "กฎหมาย", "ทำเนียบ", "opposition", "parliament", "cabinet", "prime minister",
        "election", "coup", "junta", "senate", "constitution", "no-confidence", "thai government", "pheu thai", "people's party",
    ],
    "governance": [
        "ผู้ว่าฯ", "ผู้ว่าราชการ", "มหาดไทย", "อบต.", "อบจ.", "เทศบาล", "นายอำเภอ", "กำนัน", "ผู้ใหญ่บ้าน", "ท้องถิ่น",
        "ราชการ", "ข้าราชการ", "ทุจริต", "คอร์รัปชัน", "โกง", "ฮั้ว", "เรียกรับ", "สินบน", "ส่วย", "ตรวจสอบ", "ปลด", "โยกย้าย",
        "คำสั่ง", "ประกาศ", "มาตรการ", "นโยบาย", "ตำรวจ", "ตร.", "ทหาร", "ศาล", "อัยการ", "ดีเอสไอ", "สตง.", "กฤษฎีกา",
        "เคอร์ฟิว", "ฉุกเฉิน", "กฎอัยการศึก", "ชายแดน", "ผู้ลี้ภัย", "แรงงานข้ามชาติ", "ผลักดัน", "governor", "ministry",
        "corruption", "bribe", "police", "curfew", "martial law", "border", "refugee", "emergency decree", "myanmar", "junta",
    ],
    "hardship": [
        "เดือดร้อน", "ร้องเรียน", "ร้องทุกข์", "ร้องขอ", "ชาวบ้าน", "ชาวนา", "เกษตรกร", "ชาวสวน", "ชาวประมง", "ประชาชน", "ผู้บริโภค",
        "ราคาตก", "ราคาพืชผล", "ราคาข้าว", "ราคายาง", "ราคาปาล์ม", "ค่าครองชีพ", "ค่าไฟ", "ค่าน้ำมัน", "แพง", "ขาดแคลน", "หนี้",
        "หนี้นอกระบบ", "ตกงาน", "เลิกจ้าง", "ปิดโรงงาน", "ไล่รื้อ", "ไล่ที่", "ที่ดินทำกิน", "สปก.", "เวนคืน", "น้ำแล้ง", "ภัยแล้ง",
        "ขาดน้ำ", "ไฟดับ", "น้ำประปาไม่ไหล", "ถนนพัง", "สะพานขาด", "ค่าแรง", "ค่าจ้าง", "เยียวยา", "ชดเชย", "ค่าชดเชย",
        "มลพิษ", "ฝุ่น", "PM2.5", "กลิ่นเหม็น", "น้ำเสีย", "สารเคมี", "รั่วไหล", "ผลกระทบ", "โรงงาน", "เหมือง", "โรงไฟฟ้า",
        "ยาเสพติด", "ผู้ป่วยติดเตียง", "ผู้พิการ", "ผู้สูงอายุ", "เบี้ยยังชีพ", "บัตรสวัสดิการ", "farmers", "villagers", "complaint",
        "eviction", "layoff", "debt", "pollution", "compensation", "hardship", "cost of living",
    ],
    "disaster": [
        "น้ำท่วม", "น้ำป่า", "น้ำหลาก", "อุทกภัย", "ดินถล่ม", "ดินสไลด์", "โคลนถล่ม", "แผ่นดินไหว", "อาฟเตอร์ช็อก", "สึนามิ",
        "พายุ", "ไต้ฝุ่น", "ดีเปรสชัน", "มรสุม", "ฝนตกหนัก", "ลมกระโชก", "ลูกเห็บ", "คลื่นลมแรง", "ไฟไหม้", "เพลิงไหม้",
        "ไฟป่า", "ระเบิด", "ก๊าซรั่ว", "สารเคมีรั่ว", "ตึกถล่ม", "อาคารถล่ม", "สะพานถล่ม", "เขื่อนแตก", "อพยพ", "เตือนภัย",
        "ปภ.", "กรมอุตุ", "ประกาศเตือน", "พื้นที่ประสบภัย", "เขตภัยพิบัติ", "ภัยพิบัติ", "ภัยแล้ง", "คลื่นความร้อน", "หมอกควัน",
        "โรคระบาด", "ระบาด", "ไข้เลือดออก", "ไข้หวัดนก", "อหิวาต์", "โควิด", "ผู้เสียชีวิต", "เสียชีวิต", "สูญหาย", "บาดเจ็บ",
        "อุบัติเหตุหมู่", "รถบัส", "รถไฟตกราง", "เครื่องบินตก", "เรือล่ม", "flood", "flash flood", "landslide", "earthquake",
        "tsunami", "storm", "typhoon", "cyclone", "wildfire", "explosion", "collapse", "evacuat", "outbreak", "disaster",
    ],
    "protest": [
        "ชุมนุม", "ประท้วง", "คัดค้าน", "ต่อต้าน", "รวมตัว", "เดินขบวน", "เคลื่อนขบวน", "ปิดถนน", "ปิดล้อม", "บุก", "ยื่นหนังสือ",
        "ยื่นข้อเรียกร้อง", "เรียกร้อง", "ข้อเรียกร้อง", "ม็อบ", "ผู้ชุมนุม", "แกนนำ", "นัดหมาย", "นัดรวมพล", "แฟลชม็อบ", "ปราศรัย",
        "อดอาหาร", "อารยะขัดขืน", "สไตรค์", "หยุดงาน", "นัดหยุดงาน", "ล่ารายชื่อ", "ลงชื่อคัดค้าน", "ไม่เอา", "ไล่", "ขับไล่",
        "ต้าน", "เผา", "ปะทะ", "สลายการชุมนุม", "แก๊สน้ำตา", "จับกุมผู้ชุมนุม", "ควบคุมฝูงชน", "คฝ.", "เครือข่าย", "สมัชชา",
        "สหภาพ", "สหพันธ์", "กลุ่มอนุรักษ์", "ภาคประชาชน", "ภาคประชาสังคม", "เอ็นจีโอ", "NGO", "protest", "rally", "demonstrat",
        "march", "strike", "oppose", "activist", "petition", "crackdown", "tear gas", "mob", "sit-in",
    ],
}

# คำที่ทำให้ระดับสูงขึ้น
ESSENTIAL_WORDS = ["ประกาศเขต", "ภัยพิบัติ", "ภาวะฉุกเฉิน", "พ.ร.ก.ฉุกเฉิน", "เคอร์ฟิว", "กฎอัยการศึก", "อพยพ", "เตือนภัย", "สึนามิ",
                   "แผ่นดินไหว", "เสียชีวิต", "สูญหาย", "ระเบิด", "ยุบสภา", "รัฐประหาร", "สลายการชุมนุม", "ปะทะ", "เขื่อนแตก",
                   "ประกาศพื้นที่", "ด่วน", "ด่วนที่สุด", "breaking", "emergency", "evacuat", "curfew", "coup", "dissolve"]
IMPORTANT_WORDS = ["อภิปราย", "ไม่ไว้วางใจ", "ครม.", "มติ", "ศาลรัฐธรรมนูญ", "เลือกตั้ง", "ประกาศเตือน", "ฝนตกหนัก", "น้ำท่วม",
                   "ดินถล่ม", "ชุมนุม", "ประท้วง", "คัดค้าน", "รวมตัว", "เคลื่อนขบวน", "ปิดถนน", "เรียกร้อง", "ไล่รื้อ", "ทุจริต", "cabinet", "protest",
                   "flood", "landslide", "no-confidence", "election"]

# คำที่บ่งชี้ว่าเป็นข่าวบันเทิง/กีฬา/ไลฟ์สไตล์ → ลดคะแนน
NOISE_WORDS = ["ดารา", "นักแสดง", "ซีรีส์", "ละคร", "คอนเสิร์ต", "ศิลปิน", "เพลง", "ฟุตบอล", "พรีเมียร์ลีก", "วอลเลย์บอล", "ดวง",
               "ราศี", "หวย", "เลขเด็ด", "สลาก", "รีวิว", "โปรโมชั่น", "แฟชั่น", "ความงาม", "สูตรอาหาร", "ท่องเที่ยว", "บอลโลก",
               "celebrity", "recipe", "football", "horoscope", "lottery", "k-pop"]

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']+")


@lru_cache(maxsize=1)
def _custom_keywords():
    """คำเพิ่มเติมจาก DB (แคชไว้; เรียก reset_cache() เมื่อแก้ไข)"""
    out = {c: [] for c in DEFAULT_KEYWORDS}
    disabled = set()
    try:
        for k in Keyword.query.filter_by(kind="classify").all():
            if not k.enabled:
                disabled.add(k.word.lower())
            elif k.category in out:
                out[k.category].append(k.word)
    except Exception:
        pass
    return out, disabled


def reset_cache():
    _custom_keywords.cache_clear()


def _contains(text_l: str, word: str) -> bool:
    w = word.lower()
    if _TOKEN_RE.fullmatch(w):
        # คำอังกฤษ: ต้องขึ้นต้นคำ (กัน "mob" ไปเจอใน "mobile")
        return re.search(r"(?<![a-z])" + re.escape(w), text_l) is not None
    return w in text_l


def classify(title: str, summary: str = "") -> dict:
    """คืน {'categories': [...], 'primary': str|None, 'level': str, 'matched': [...], 'score': float}"""
    text = f"{title or ''} {summary or ''}"
    text_l = text.lower()
    title_l = (title or "").lower()
    custom, disabled = _custom_keywords()

    scores, matched = {}, {}
    for cat, words in DEFAULT_KEYWORDS.items():
        s = 0.0
        hits = []
        for w in list(words) + custom.get(cat, []):
            if w.lower() in disabled:
                continue
            if _contains(text_l, w):
                s += 2.0 if _contains(title_l, w) else 1.0
                hits.append(w)
        if s > 0:
            scores[cat] = s
            matched[cat] = hits

    noise = sum(1 for w in NOISE_WORDS if _contains(text_l, w))
    for cat in list(scores):
        scores[cat] -= noise * 1.5
        if scores[cat] <= 0:
            scores.pop(cat)
            matched.pop(cat, None)

    # ต้องมีคะแนนอย่างน้อย 2 (เจอในหัวข้อ 1 คำ หรือในเนื้อ 2 คำ) ถึงนับว่าเข้าหมวด
    cats = [c for c, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s >= 2]
    primary = cats[0] if cats else None
    all_hits = sorted({w for c in cats for w in matched.get(c, [])})

    level = "interesting"
    if any(_contains(text_l, w) for w in ESSENTIAL_WORDS) and primary in ("disaster", "protest", "politics", "governance"):
        level = "essential"
    elif any(_contains(text_l, w) for w in IMPORTANT_WORDS):
        level = "important"
    elif primary:
        level = "should_know"
    # ระดับสูงสุดต้องเจอคำในหัวข้อ ไม่ใช่แค่เนื้อ
    if level == "essential" and not any(_contains(title_l, w) for w in ESSENTIAL_WORDS):
        level = "important"

    return {"categories": cats, "primary": primary, "level": level, "matched": all_hits,
            "score": max(scores.values()) if scores else 0.0}
