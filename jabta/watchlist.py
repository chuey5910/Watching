"""อ่านรายชื่อเพจ/บุคคลที่ต้องเฝ้าระวังจากไฟล์ PDF แล้วแยกประเภท

ตาราง 4 คอลัมน์: จังหวัด | กลุ่ม/บุคคล | Facebook/URL | Line/URL

การแกะ PDF ภาษาไทยมีปัญหาสองอย่างที่ต้องจัดการคนละทาง
- pdfplumber อ่านโครงสร้างตารางถูก แต่สระ/วรรณยุกต์สลับที่ (กลุ่ม -> กลมุ่)
- pypdf อ่านไทยถูก แต่จับคู่แถวเพี้ยนเมื่อชื่อขึ้นสองบรรทัด
จึงใช้ pdfplumber เป็นโครง แล้วหาข้อความที่ถูกต้องจาก pypdf มาแทน
โดยเทียบด้วย "ชุดตัวอักษร" เพราะข้อความที่สลับที่มีตัวอักษรชุดเดียวกัน
"""
import re

URL_RE = re.compile(r"https?://[^\s]+")

# คำที่บ่งว่าเป็นบุคคล
PERSON_PREFIX = ("นาย", "นาง", "นางสาว", "น.ส.", "ดร.", "ส.ส.", "สส.", "ส.ว.",
                 "ทนาย", "พล.", "ร.ต.", "พ.ต.", "ผศ.", "รศ.", "ศ.")
PERSON_WORDS = ("แกนนำ", "ผู้สมัคร", "สมาชิกพรรค", "นักวิชาการ", "ผู้ใหญ่บ้าน", "กำนัน")

# คำที่บ่งว่าเป็นเพจ/องค์กร
PAGE_STARTERS = ("เพจ", "กลุ่ม", "ชมรม", "สมาคม", "มูลนิธิ", "เครือข่าย", "สภา", "พรรค",
                 "สมัชชา", "ศูนย์", "คณะ", "สกน.", "สกท.", "กป.อพช.", "ขบวนการ", "สหภาพ")

PAGE_WORDS = ("เพจ", "กลุ่ม", "ชมรม", "สมาคม", "มูลนิธิ", "เครือข่าย", "สภา", "พรรค",
              "สมัชชา", "ศูนย์", "คณะ", "องค์กร", "ขบวนการ", "สหภาพ", "สหพันธ์",
              "สกน.", "สกท.", "กป.อพช.", "ngo", "movement", "council", "party", "network")

# URL ที่ไม่ใช่หน้าโปรไฟล์ ใช้เฝ้าติดตามไม่ได้
BAD_URL = [
    ("/photo/", "ลิงก์ชี้ไปที่รูปภาพ ไม่ใช่หน้าโปรไฟล์"),
    ("/search/", "ลิงก์ชี้ไปที่หน้าค้นหา ไม่ใช่หน้าโปรไฟล์"),
    ("/posts/", "ลิงก์ชี้ไปที่โพสต์เดียว ไม่ใช่หน้าโปรไฟล์"),
    ("/share/p/", "ลิงก์แชร์โพสต์เดียว ไม่ใช่หน้าโปรไฟล์"),
    ("/share/v/", "ลิงก์แชร์วิดีโอเดียว ไม่ใช่หน้าโปรไฟล์"),
]


def _key(s: str):
    return tuple(sorted(re.sub(r"\s+", "", s)))


def extract_rows(path: str) -> list[dict]:
    import pdfplumber
    from pypdf import PdfReader

    ref = {}
    for pg in PdfReader(path).pages:
        for ln in (pg.extract_text() or "").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("http"):
                ref.setdefault(_key(ln), ln)

    rows = []
    with pdfplumber.open(path) as pdf:
        for pi, pg in enumerate(pdf.pages, 1):
            for table in pg.extract_tables():
                for cells in table:
                    c = [(x or "").replace("\n", " ").strip() for x in cells]
                    if not any(c) or c[0].startswith(("จังหวัด", "จงั")):
                        continue
                    prov, label = c[0], (c[1] if len(c) > 1 else "")
                    text = ref.get(_key(prov + label)) or f"{prov} {label}".strip()
                    urls = URL_RE.findall(" ".join(c))
                    # ข้อความที่ปนอยู่ในช่อง URL มักเป็นชื่อคนที่ตกมาจากช่องซ้าย
                    tail = " ".join(URL_RE.sub(" ", x) for x in c[2:]).strip()
                    rows.append({"page": pi, "province": prov, "text": text,
                                 "urls": urls, "extra": tail})
    return rows


def strip_province(text: str) -> str:
    """ตัดชื่อจังหวัดที่นำหน้าออก เพราะข้อความจาก PDF รวม 'จังหวัด + ชื่อ' ไว้ด้วยกัน
    ถ้าไม่ตัด คำนำหน้าอย่าง 'นาย' จะไม่ได้อยู่ต้นสตริง ทำให้แยกบุคคลไม่ออก
    """
    t = text.strip()
    try:
        from pythainlp.corpus import provinces
        provs = sorted(provinces(), key=len, reverse=True)
    except Exception:
        provs = []
    for pv in provs:
        if t.startswith(pv):
            return t[len(pv):].strip()
    # ชื่อจังหวัดที่สระ/วรรณยุกต์เพี้ยนจากการแกะ PDF (เชียงใหม ่) ยังตัดได้
    # เพราะตัวอักษรเป็นชุดเดียวกัน ต่างแค่ลำดับและช่องว่างที่แทรกเข้ามา
    for pv in provs:
        want = _key(pv)
        for extra in range(0, 4):
            head = t[: len(pv) + extra]
            if _key(head) == want:
                return t[len(pv) + extra :].strip()
    return t


def classify(text: str, url: str = "") -> tuple[str, str, str]:
    """คืน (ประเภท, ความมั่นใจ, เหตุผล) — ประเภท: person / page / group / unknown"""
    u = url.lower()
    if "/groups/" in u:
        return "group", "สูง", "URL เป็นกลุ่ม Facebook"

    label = strip_province(text)
    label = re.sub(r"^[\d.\s]+", "", label)       # ตัดเลขลำดับ "1." ออก
    t = label.lower()

    if label.startswith(PERSON_PREFIX):
        return "person", "สูง", f"ขึ้นต้นด้วยคำนำหน้า"
    if label.startswith(PAGE_STARTERS):
        return "page", "สูง", f"ขึ้นต้นด้วยคำบ่งองค์กร"
    if any(p in label for p in PERSON_PREFIX):
        return "person", "สูง", "มีคำนำหน้าบุคคลอยู่ในข้อความ"
    if any(w in t for w in PERSON_WORDS):
        return "person", "กลาง", "มีคำบ่งตำแหน่งบุคคล"
    if any(w in t for w in PAGE_WORDS):
        return "page", "กลาง", "มีคำบ่งองค์กร"

    # ไม่มีคำบ่งชัด ใช้คลังชื่อคนไทยช่วย
    try:
        from pythainlp.corpus import thai_female_names, thai_male_names, thai_family_names
        names = set(thai_female_names()) | set(thai_male_names())
        fams = set(thai_family_names())
        parts = [x for x in re.split(r"[\s/()\-]+", label) if x]
        if len(parts) >= 2 and parts[0] in names and parts[1] in fams:
            return "person", "สูง", "ชื่อ-นามสกุลตรงกับคลังชื่อคนไทย"
        if parts and parts[0] in names:
            return "person", "กลาง", "ชื่อต้นตรงกับคลังชื่อคนไทย"
    except Exception:
        pass

    if "profile.php" in u:
        return "unknown", "ต่ำ", "URL เป็น profile.php ใช้ได้ทั้งคนและเพจ"
    return "unknown", "ต่ำ", "ไม่มีคำบ่งชี้"


def url_note(url: str) -> str:
    u = url.lower()
    for frag, msg in BAD_URL:
        if frag in u:
            return msg
    if "/share/" in u:
        return "ลิงก์แชร์ ต้องตามต่อเพื่อหา URL จริง"
    return ""
