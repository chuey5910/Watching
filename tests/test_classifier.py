"""ชุดทดสอบตัวจัดหมวด — หัวข้อทั้งหมดมาจากข่าวจริงในระบบ (flask classify-audit)

รันด้วย: TAILSCALE_ONLY=0 DISABLE_SCHEDULER=1 python -m pytest tests/ -q
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from jabta import create_app
from jabta.classifier import classify

app = create_app()

# (หัวข้อ, หมวดที่ควรได้) — None = ไม่ควรเข้าหมวดใดเลย
CASES = [
    # --- ควรเข้าหมวด ---
    ("ครม.เห็นชอบ 'บ้านประหยัดพลังงาน' มูลค่า 1,050 ลบ. ยกระดับบ้านทั่วไทย", "politics"),
    ("ลุยงานถนัด! 'ไอซ์' ปลุกนายจ้าง-ลูกจ้าง เหลือ 7 วัน ออกใช้สิทธิเลือกตั้ง", "politics"),
    ("Flash Floods hit Thailand's Nan Province", "disaster"),
    ("ไฟไหม้ โกดังโรงสีทวีรวมมิตร ขนรถดับเพลิงกว่า 50 คัน แต่ยังคุมเพลิง", "disaster"),
    ("น้ำเหนือทะลัก! ซัดคันคลองพัง นาข้าวชัยนาท จมมิดกว่าพันไร่", "disaster"),  # น้ำท่วม = ภัยพิบัติ แม้ผลกระทบจะตกกับเกษตรกร,
    ("ประชาชนขึ้นฟลอร์ ปราศรัย เรียกร้อง #สั่งฟ้อง229", "protest"),
    ("ภาคการผลิตดั้งเดิมเสี่ยงปิดโรงงาน ผวาสายป่านธุรกิจสั้น", "hardship"),
    ("ชาวบ้านรวมตัวชุมนุมคัดค้านโครงการเหมืองแร่โปแตช", "protest"),
    ("กรมป้องกันและบรรเทาสาธารณภัยประกาศเขตพื้นที่ประสบสาธารณภัย", "disaster"),

    # --- ไม่ควรเข้าหมวด (ข่าวอาชญากรรม/บันเทิง/ธุรกิจที่หลุดเข้ามา) ---
    ("Bentley changes Vietnam distributor to Pon Phu Thai Mobility, cust", None),
    ("'BILLKIN' บุกเมืองโตเกียว พบแฟนๆ ชาวญี่ปุ่นสุดใกล้ชิด", None),
    ("ข่าวนาทีบุกจับผู้ต้องหาฆ่าโหดกิ๊กสาว", None),
    ("สิ้นสุดการรอคอย! ไดมอนด์ ณรกร ประกาศอัลบั้มเดี่ยว PRAEW PROW", None),
    ("หนุ่มป่วยจิตเวชคลั่ง ถือมีดบุกจะปล้ำเมียชาวบ้าน ผัวสู้ไม่ได้คว้าปืน", None),
    ("ข่าวต่อเพชฌฆาต ต่อยชาวบ้านดับ", None),
    ("War-bruised Myanmar finds relief in bareknuckle bloodsport", None),
]

# หัวข้อที่ไม่ควรได้ระดับ "จำเป็น"
NOT_ESSENTIAL = [
    "สหรัฐฯ-จีน ตั้งช่องทางเตือนภัย AI โหมโรงก่อนซัมมิต 'ทรัมป์-สี'",
]


def run():
    ok = bad = 0
    with app.app_context():
        for title, want in CASES:
            got = classify(title)["primary"]
            good = (got == want)
            ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
            if not good:
                r = classify(title)
                print(f"  ผิด  ได้ {str(got):12} ควรได้ {str(want):12} | {title[:52]}")
                print(f"       คำที่เจอ: {','.join(r['matched'])[:90]}")
        for title in NOT_ESSENTIAL:
            lv = classify(title)["level"]
            good = lv != "essential"
            ok, bad = (ok + 1, bad) if good else (ok, bad + 1)
            if not good:
                print(f"  ผิด  ระดับ {lv} ไม่ควรเป็น essential | {title[:52]}")
    total = len(CASES) + len(NOT_ESSENTIAL)
    print(f"\nผ่าน {ok}/{total}" + (f"  ตก {bad}" if bad else "  ผ่านหมด"))
    return bad


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
