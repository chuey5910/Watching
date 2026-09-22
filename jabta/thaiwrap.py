"""ตัดคำไทยเพื่อกำหนดจุดขึ้นบรรทัดใหม่

เบราว์เซอร์มองข้อความไทยที่ไม่มีช่องว่างเป็นคำเดียวทั้งก้อน เวลาคำนั้นยาวเกิน
ความกว้างคอลัมน์มันจะหั่นกลางคำ ("ยิ่งลักษณ์" กลายเป็น "ยิ่ง/ลักษณ์")
แก้โดยแทรกช่องว่างความกว้างศูนย์ (U+200B) ตรงรอยต่อคำที่ตัดได้จริง
เบราว์เซอร์จะขึ้นบรรทัดใหม่ได้เฉพาะตรงจุดนั้น ตัวอักษรที่แสดงไม่เปลี่ยน
"""
from functools import lru_cache

ZWSP = "​"

# ชื่อบุคคล/องค์กร/ศัพท์ข่าวที่ยังไม่มีในพจนานุกรมมาตรฐาน — เติมได้เรื่อย ๆ
EXTRA_WORDS = {
    "แพทองธาร", "อุ๊งอิ๊ง", "ธนาธร", "ปิยบุตร", "พรรณิการ์", "ชัยธวัช",
    "ศาลปกครองสูงสุด", "ศาลรัฐธรรมนูญ", "ศาลอาญาคดีทุจริต",
    "จำนำข้าว", "เงินดิจิทัล", "แลนด์บริดจ์", "โปแตช", "เหมืองแร่",
    "ประชามติ", "ยุบสภา", "อภิปรายไม่ไว้วางใจ", "นิรโทษกรรม",
    "ภูมิใจไทย", "เพื่อไทย", "ก้าวไกล", "ประชาชน", "ประชาธิปัตย์", "รวมไทยสร้างชาติ",
    "เมียนมา", "ว้าแดง", "สแกมเมอร์", "ชเวโก๊กโก", "เมียวดี",
}

_trie = None


def _get_trie():
    """สร้าง trie ครั้งเดียวตอนเรียกใช้ครั้งแรก — รวมคำทั่วไปกับคลังชื่อคนไทย"""
    global _trie
    if _trie is None:
        from pythainlp.corpus import thai_words
        from pythainlp.util import dict_trie
        words = set(thai_words()) | set(EXTRA_WORDS)
        for loader in ("thai_female_names", "thai_male_names", "thai_family_names"):
            try:
                import pythainlp.corpus as c
                words |= set(getattr(c, loader)())
            except Exception:
                pass
        _trie = dict_trie(words)
    return _trie


def has_thai(text: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in text)


@lru_cache(maxsize=4096)
def thai_zwsp(text: str) -> str:
    """คืนข้อความเดิมที่แทรก U+200B ตรงรอยต่อคำ ถ้าไม่ใช่ภาษาไทยคืนของเดิม"""
    if not text or not has_thai(text):
        return text or ""
    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm", custom_dict=_get_trie())
    except Exception:
        return text
    out = []
    for i, tok in enumerate(tokens):
        if i and tok.strip() and out and out[-1].strip() and _breakable_before(tok):
            out.append(ZWSP)
        out.append(tok)
    return "".join(out)


def _breakable_before(tok: str) -> bool:
    """ห้ามขึ้นบรรทัดใหม่ถ้าจะทำให้บรรทัดใหม่เริ่มด้วยเครื่องหมายวรรคตอน

    เช่น 'ปค.' ต้องไม่กลายเป็น 'ปค' ท้ายบรรทัดแล้ว '.' ขึ้นต้นบรรทัดถัดไป
    ส่วนการขึ้นบรรทัดใหม่ "หลัง" เครื่องหมายวรรคตอนยอมได้ (ปค. / สูงสุด)
    """
    ch = tok[0]
    return ch.isalnum() or "\u0e00" <= ch <= "\u0e7f"
