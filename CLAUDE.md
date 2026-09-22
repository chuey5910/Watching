# CLAUDE.md — เอกสารส่งมอบงาน "จับตา." (อ่านไฟล์นี้ก่อนแตะโค้ด)

> ไฟล์นี้เขียนโดย Claude (Cowork) เพื่อส่งงานต่อให้ Claude Code — รวมบริบทโครงการ การตัดสินใจเชิงออกแบบ สถานะที่ทดสอบแล้ว/ยังไม่ได้ทดสอบ ปัญหาที่รู้ และงานถัดไป ทั้งหมดอยู่ในไฟล์เดียว
> ผู้ใช้ชื่อ **Chuey** สื่อสารภาษาไทยเป็นหลัก (สลับอังกฤษได้) ถนัด Flask / LINE OA / งานวิเคราะห์ข่าวความมั่นคง — ตอบและเขียนคอมเมนต์/ข้อความใน UI เป็น**ภาษาไทย** โค้ด identifier เป็นอังกฤษ

---

## 0. TL;DR

- **อะไร:** เว็บกระดานข่าว self-hosted ชื่อ "จับตา." (jabta) รวบรวมข่าว 5 หมวด (การเมือง / การปกครอง / ความเดือดร้อนประชาชน / ภัยพิบัติ / ชุมนุม-ประท้วง-คัดค้าน) จากสื่อหลัก สื่อท้องถิ่น สื่อต่างประเทศ หน่วยงานรัฐ และบัญชีโซเชียลบุคคล → จับกลุ่มข่าวเดียวกัน → จัดระดับ (จำเป็น/สำคัญ/สมควรรู้/น่าสนใจ) → ผู้ใช้ **ปักหมุดข่าวให้ขึ้นบนสุด** ได้เองและด้วยกฎอัตโนมัติ
- **เข้าถึง:** เฉพาะใน **Tailscale Tailnet** · สมัครแล้ว **รอ admin อนุมัติ** · **บันทึก log** ทุกอย่าง
- **สแตก:** Python 3.11+ · Flask 3 · Flask-Login · Flask-SQLAlchemy (SQLite) · feedparser · requests · BeautifulSoup/lxml · APScheduler · gunicorn · Jinja templates + CSS ล้วน (ไม่มี JS framework/ไม่มี build step)
- **สถานะ:** โค้ดครบทุกฟีเจอร์ ทดสอบ end-to-end ผ่านกับ **ฟีดจำลองในเครื่อง** และ Flask test client · **ยังไม่เคยดึงฟีดจริง 148 แหล่ง** (sandbox ที่สร้างไม่มีเน็ตออก) → งานแรกของ Claude Code คือรันจริงแล้วไล่แก้แหล่งที่ "ดึงไม่ได้" (ดูข้อ 8)
- **เริ่มรัน:** `./scripts/install.sh && ./scripts/run.sh` → http://127.0.0.1:8085 → สมัครบัญชีแรก = admin → กด "ดึงข่าวตอนนี้" → `./scripts/tailscale-serve.sh`

---

## 1. ความต้องการจากผู้ใช้ (ตามคำพูดเดิม สรุปครบ)

1. หน้ากระดานข่าวออนไลน์ หน้าตา **ไม่เหมือนใคร ดูน่าสนใจ ดึงดูดให้อ่าน**
2. **เลือก/กำหนดข่าวที่น่าสนใจเป็นพิเศษให้แสดงบนสุดได้**
3. แหล่งข่าว = **สื่อออนไลน์หลักทั้งหมด + สื่อท้องถิ่น ทั้งในและต่างประเทศ** และ **เพิ่มสื่อที่ต้องการติดตามบนเว็บได้เลย**
4. **เพิ่มสื่อโซเชียลของบุคคลเพื่อเฝ้าติดตามได้**
5. หัวข้อข่าว: **การเมือง การปกครอง ความเดือดร้อนของประชาชน/ชาวบ้าน ภัยพิบัติ การรวมตัวชุมนุม ประท้วง ต่อต้าน คัดค้าน**
6. มีส่วน **"สำคัญ / สมควรรู้ / น่าสนใจ / จำเป็น"** เพิ่มเข้ามา
7. (รอบสอง) **ระบบเข้าสู่ระบบ · ใช้ Tailscale · บันทึก log · รอการอนุมัติหลังสมัคร**
8. ผู้ใช้อนุมัติรายชื่อสื่อที่เสนอ (ดูข้อ 6) ว่า "ครบถ้วน"

ก่อนสร้าง มี mockup 3 หน้าจอบน Design canvas (artifact "กระดานข่าวเฝ้าระวัง — Mockup") ซึ่งผู้ใช้เห็นแล้วและสั่งทำต่อโดยไม่ขอแก้ — โค้ดจริงทำตาม mockup นั้น

---

## 2. โครงสร้างโปรเจกต์

```
jabta/
├── app.py                 จุดเริ่ม: create_app() + scheduler.start()  (python app.py หรือ gunicorn app:app)
├── config.py              Config จาก env/.env (โหลด python-dotenv ถ้ามี)
├── gunicorn.conf.py       1 worker × 8 threads (scheduler อยู่ในโปรเซสเดียว — ห้ามเพิ่ม worker โดยไม่ย้าย scheduler ออก)
├── requirements.txt · .env.example · .gitignore · Dockerfile · docker-compose.yml (มี Tailscale sidecar)
├── README.md              คู่มือผู้ใช้ภาษาไทย (ติดตั้ง / Tailscale / ผู้ใช้ / log / แหล่งข่าว / กฎ / LINE / CLI)
├── scripts/
│   ├── install.sh         venv + pip + .env (สุ่ม SECRET_KEY) + flask seed   ← ทดสอบรันจากศูนย์แล้วผ่าน
│   ├── run.sh             gunicorn
│   ├── tailscale-serve.sh tailscale serve --bg --https=443 http://127.0.0.1:8085
│   ├── jabta.service      systemd (Linux)      ├── com.jabta.board.plist  launchd (macOS/Mac mini)
│   └── ts-serve.json      serve config สำหรับ Tailscale sidecar ใน docker-compose
├── data/jabta.sqlite3     (สร้างตอนรัน)        logs/app.log · audit.log · access.log (RotatingFileHandler)
└── jabta/
    ├── __init__.py        create_app: logging 3 ไฟล์, before_request (Tailnet gate + TS auto-login), after_request (access log),
    │                      Jinja filters (fmt_time/ago/thai_date → เวลาไทย UTC+7), error 403/404, CLI: seed/fetch/create-admin/approve/morning-brief
    ├── models.py          User, Source, Story, Article, Pin, Rule, Keyword, AuditLog, FetchLog, Setting + ค่าคงที่ CATEGORIES/LEVELS/SOURCE_TYPES/FETCH_KINDS
    ├── security.py        client_ip() (X-Forwarded-For เฉพาะจาก loopback), is_trusted_ip() (100.64/10, fd7a:115c:a1e0::/48, loopback, EXTRA_TRUSTED_CIDRS),
    │                      tailscale_identity() (เชื่อ header เฉพาะจาก loopback), enforce_tailscale_gate(), audit(), admin_required
    ├── auth.py            /login /register /pending /logout /account · try_tailscale_autologin() · lockout
    ├── views.py           ทุกหน้า: / (board), /story/<id>, pin/unpin/reorder/update, /sources (+add/edit/toggle/delete/fetch/detect),
    │                      /curate, rules, keywords, /fetch-now, /admin/users (+actions), /admin/logs
    ├── fetcher.py         run_fetch() ขนานด้วย ThreadPool → fetch_source() ตามชนิด → store_items() (classify + dedupe + cluster + alert flag)
    ├── classifier.py      keyword-based: DEFAULT_KEYWORDS 5 หมวด (ไทย+อังกฤษ), ESSENTIAL/IMPORTANT/NOISE words, classify() → categories/primary/level/matched
    ├── cluster.py         normalize() + character-trigram Jaccard + containment → assign_story() / refresh_story() (source_count, local_first, score)
    ├── rules.py           pin_story(), renumber_pins() (MAX_PINS=5), apply_rules(), expire_pins(), send_alerts(), morning_brief_text()
    ├── scheduler.py       APScheduler: fetch_job ทุก FETCH_INTERVAL_MINUTES, morning brief cron
    ├── line.py            push_text() ผ่าน LINE Messaging API (เงียบถ้าไม่ตั้ง token)
    ├── seed_sources.py    รายชื่อสื่อ 148 แหล่ง + DEFAULT_RULES 4 ข้อ + DEFAULT_WATCH คำสำคัญ
    ├── static/style.css   ดีไซน์ทั้งหมด (CSS variables, responsive ≤1200px)
    └── templates/         base.html, board.html, story.html, sources.html, source_edit.html, _source_form.html, _source_form_js.html,
                           curate.html, admin_users.html, admin_logs.html, error.html, auth/{_layout,login,register,pending,account}.html
```

---

## 3. ดีไซน์ (ต้องรักษาไว้ — ผู้ใช้อนุมัติหน้าตานี้แล้ว)

- โทน **เข้มแบบห้องติดตามสถานการณ์**: พื้น `#0F1116`, panel `#15181F`, เส้น `#2A2E39`, ตัวอักษรครีม `#F2ECDD`, สีเน้น **ส้มแดง `#E4572E`** ใช้เฉพาะ "ด่วน/ปักหมุด #1/จำเป็น"
- ฟอนต์: หัวข้อ **Chonburi** (Google Fonts, display ไทย) · เนื้อหา **IBM Plex Sans Thai** — โหลดผ่าน `@import` ใน style.css (เครื่องที่ไม่มีเน็ตออก Google จะ fallback เป็น serif/system)
- สีประจำหมวด (อยู่ทั้งใน `models.CATEGORIES` และ CSS vars `--c-*`): การเมือง ทอง `#F0A868` · การปกครอง ฟ้า `#7FB7E6` · ความเดือดร้อน เขียว `#8ED3A4` · ภัยพิบัติ แดง `#E4572E` · ชุมนุม ม่วง `#C08BF0`
- สีระดับ (`models.LEVELS`, `--l-*`): จำเป็น `#E4572E` · สำคัญ `#B8551E` · สมควรรู้ `#2F6F8F` · น่าสนใจ `#3E8E5A` — แถบ "สมควรรู้วันนี้" เป็นพื้นครีมกลับสี
- เลย์เอาต์กระดาน: แถบ ticker "ด่วน" → grid 3 คอลัมน์ `300px | 1fr | 320px` (ซ้าย=หมุด/คำสำคัญ/พื้นที่, กลาง=hero + เลนหมวด + สมควรรู้, ขวา=โซเชียลบุคคล/แหล่งที่รายงานมาก/ปุ่มดึง)
- ปุ่ม "📌 ปักหมุด" โผล่เมื่อ hover การ์ด (`.pinbtn`) → JS ใน base.html ยิง POST `/pin/<story_id>` (header `X-Requested-With: fetch`) แล้ว reload
- ไม่ใช้ emoji ใน UI ยกเว้นไอคอนหมุด 📌 บนปุ่ม hover และข้อความ LINE

---

## 4. โมเดลข้อมูล (สำคัญเวลาแก้)

| ตาราง | หน้าที่ | จุดที่ควรรู้ |
|---|---|---|
| `users` | บัญชี | `status`: pending/approved/rejected/disabled · `role`: admin/member · `tailscale_login` ผูกตัวตน TS · `is_active` คืน True เฉพาะ approved (Flask-Login จึงกัน pending เอง) · `failed_logins`/`locked_until` |
| `sources` | แหล่งข่าว/บัญชี | `source_type`: mainstream/local/foreign/government/social · `fetch_kind`: rss/html/gnews/gnews_query/telegram/youtube/bluesky/rsshub · `feed_url` มีความหมายต่างกันตาม kind (RSS url / โดเมน / คำค้น / channel id) · `resolved_feed_url` = url ที่ค้นพบ/fallback จริง · `categories` (คั่น ,) หมวดที่ให้เก็บ · `keep_all` ข้ามการกรอง · `alert_categories`/`alert_keywords` → `Article.is_alert` · `group_name` กลุ่มบัญชี (ใช้กับกฎ) · `etag`/`modified` conditional GET |
| `articles` | ข่าวรายชิ้น | `url_hash` sha1(canonical_url) unique = dedupe · `category` หลัก + `categories` ทั้งหมด · `level` · `matched_keywords` · `story_id` |
| `stories` | กลุ่มข่าวเรื่องเดียวกัน | `source_count`, `social_count`, `local_first` (ท้องถิ่น/บุคคลรายงานก่อนสื่อหลัก ≥2 ชม.), `score` (จัดอันดับ), `level` = สูงสุดในกลุ่ม, `title` เอาจากสื่อหลัก/รัฐก่อน |
| `pins` | หมุด | unique ต่อ story · `position` 1..5 · `auto_unpin`: idle12h/idle24h/tomorrow06/never · `pinned_by_id` (คน) หรือ `pinned_by_rule_id` (กฎ) |
| `rules` | กฎอัตโนมัติ | เงื่อนไข: category, min_sources, within_hours, keywords, source_type, source_group → action: pin/pin_top/flag (+notify_line, set_level) · `hits` |
| `keywords` | `kind=watch` คำที่ติดตามพิเศษ (แสดงบนกระดาน) · `kind=classify` คำเพิ่ม/ปิดสำหรับตัวจัดหมวด (มี UI เฉพาะ watch; classify แก้ผ่าน DB/โค้ด) |
| `audit_logs` | เหตุการณ์ผู้ใช้ | action, target, detail, ip (จริง), tailscale_login, user_agent, ok |
| `fetch_logs` | ทุกรอบดึงต่อแหล่ง | status, new_items, kept_items, duration_ms, message |
| `settings` | key/value | ใช้กันส่ง LINE ซ้ำ (`notified:<rule>:<story>`) |

เวลาทั้งหมดใน DB เป็น **UTC naive** (`datetime.utcnow()`); แสดงผลผ่าน filter `fmt_time`/`ago`/`thai_date` เป็นเวลาไทย +7 และ พ.ศ.

ไม่มี migration tool — ใช้ `db.create_all()` ตอนสตาร์ท ถ้าเพิ่มคอลัมน์ให้เขียน ALTER เอง หรือเพิ่ม Flask-Migrate (ยังไม่ได้ทำ)

---

## 5. การไหลของข้อมูล (fetch pipeline)

```
scheduler (ทุก 10 นาที) / ปุ่ม "ดึงข่าวตอนนี้" / flask fetch
  → run_fetch(): ThreadPool(FETCH_WORKERS=8) → fetch_source(src) ต่อแหล่ง (แต่ละ thread เปิด app_context เอง, rollback ไม่ commit)
      rss:  resolve_fetch_url → ถ้าไม่มี feed_url → discover_feed(homepage) → ไม่เจอ → gnews site:โดเมน
            ถ้าดึง feed_url พัง → discover → gnews (ถ้าพังทั้งคู่ raise พร้อมข้อความทั้งสอง)
      gnews / gnews_query: https://news.google.com/rss/search?q=...&hl=th&gl=TH&ceid=TH:th (ตัด " - ชื่อสำนัก" ท้ายหัวข้อ)
      html: เก็บ <a> ในโดเมนเดียวกันที่ข้อความยาว 22–220 ตัว
      telegram: https://t.me/s/<ch> parse .tgme_widget_message  (ถ้า feed_url เป็น http ที่ไม่ใช่ t.me จะใช้ url นั้น — ไว้ทดสอบ)
      youtube: feeds/videos.xml?channel_id= · bluesky: bsky.app/profile/<h>/rss · rsshub: RSSHUB_BASE + route
  → main thread: บันทึกสถานะแหล่ง + FetchLog แล้ว store_items():
      dedupe ด้วย url_hash → classify(title, summary) → กรองตาม src.categories (ข้ามถ้า keep_all หรือ KEEP_ONLY_MATCHED=0)
      → สร้าง Article → assign_story() (trigram Jaccard ≥0.38 หรือ containment ≥0.72 ภายใน 48 ชม., ไม่จำกัดหมวด) → refresh_story()
      → ตั้ง is_alert ถ้าเข้าหมวด/คำที่แหล่งตั้ง alert
  → apply_rules(kept_ids) → send_alerts(alert_ids) → expire_pins() → ลบข่าวเก่ากว่า ARTICLE_RETENTION_DAYS (45)
```

`run_fetch()` คืน dict ที่มี **`kept_ids` / `alert_ids` เป็น list ของ id** (ไม่ใช่ object — เคยพัง DetachedInstanceError แล้วแก้แล้ว อย่าย้อนกลับ)

---

## 6. รายชื่อสื่อเริ่มต้น (ผู้ใช้อนุมัติแล้ว) — อยู่ใน `seed_sources.py`

- **สื่อหลักในประเทศ (42):** ไทยพีบีเอส, สำนักข่าวไทย, NNT, ไทยรัฐ, ข่าวสด, มติชน, เดลินิวส์, คมชัดลึก, แนวหน้า, ผู้จัดการ, โพสต์ทูเดย์, ไทยโพสต์, บ้านเมือง, สยามรัฐ, ช่อง 3, ช่อง 7, อมรินทร์, ไทยรัฐทีวี, PPTV, เนชั่นทีวี, TNN, ONE31, Workpoint, ช่อง 8, MONO29, ประชาชาติ, กรุงเทพธุรกิจ, ฐานเศรษฐกิจ, The Standard, Thairath Plus, ประชาไท, The Momentum, The Matter, The Reporters, iLaw, อิศรา, Way, Voice, 101.world, Bangkok Post, The Nation, Khaosod English, Thai Enquirer
- **หน่วยงานรัฐ (14):** ปภ., กรมอุตุฯ, ศูนย์เตือนภัยพิบัติ, สทนช., กรมชลประทาน, Air4Thai, รัฐสภา, กกต., ศาลรัฐธรรมนูญ, ไทยคู่ฟ้า, มหาดไทย, ตร., สปข., สำนักข่าวชายขอบ(นับ local)
- **สื่อท้องถิ่น (47):** เหนือ (เชียงใหม่นิวส์, Chiang Mai One, เชียงรายโฟกัส, ลานนา, Lanner, CM108, พะเยาทีวี, แพร่นิวส์, น่านนิวส์, ตาก/แม่สอด) · อีสาน (อีสานบิซ, The Isaan Record, Khon Kaen Link, โคราชเดลี่, อุดร, อุบล, สกล, บุรีรัมย์ไทม์, หนองคาย) · กลาง/ตะวันออก/ตะวันตก (ปทุม, สุพรรณ, อยุธยา, พัทยานิวส์, The Pattaya News, ระยอง, จันท์, กาญจน์, เพชรบุรี, ราชบุรี) · ใต้ (สงขลาโฟกัส, The Phuket News, ภูเก็ตนิวส์, South Thailand News, หาดใหญ่โฟกัส, Wartani, The Motive, Deep South Watch, อามาน, สุราษฎร์, นคร, ตรัง, กระบี่) · เครือข่าย (77 ข่าวเด็ด, สยามรัฐภูมิภาค, เนชั่นภูมิภาค, ไทยพีบีเอสนักข่าวพลเมือง)
- **สื่อต่างประเทศ (45):** Reuters, AP, AFP/France24, Bloomberg, BBC Thai, BBC Asia, CNN, Al Jazeera, DW, Guardian, NYT, WaPo, FT, Economist · Nikkei Asia, SCMP, The Diplomat, CNA, Straits Times, Asia Times, Benar News, RFA, VOA Thai · เมียนมา: Irrawaddy, Myanmar Now, Mizzima, DVB, Frontier, Karen News, SHAN, BNI · เพื่อนบ้าน: Vientiane Times, Laotian Times, Khmer Times, CamboJA, Bernama, Malay Mail, FMT, VnExpress, Tuoi Tre · ภัยพิบัติ: ReliefWeb, GDACS, USGS, AHA Centre, JMA
- สื่อโลกใหญ่ใช้ `gnews_query` = `"Thailand site:โดเมน"` เพื่อกรองเฉพาะข่าวเกี่ยวไทย ไม่ให้ท่วมกระดาน
- **ชื่อโดเมน/URL RSS ของสื่อท้องถิ่นหลายรายใส่จากความจำ** (โดยเฉพาะ `xxxnews.com` ของจังหวัดต่าง ๆ) — บางโดเมนอาจไม่มีจริง ระบบจะขึ้น "ดึงไม่ได้" ให้แก้ในหน้าเว็บหรือใน seed

---

## 7. ความปลอดภัย / Tailscale / Log — พฤติกรรมที่ทดสอบยืนยันแล้ว

| กรณี | ผลที่ทดสอบได้ |
|---|---|
| คำขอจาก IP นอก Tailnet (เช่น 203.0.113.9) เมื่อ `TAILSCALE_ONLY=1` | 403 + audit `blocked_ip` |
| จาก 100.x | เข้าได้ |
| สมัครคนแรก | เป็น admin + approved + login ทันที |
| สมัครคนที่สอง | pending → login แล้ว redirect `/pending?u=` → เข้า `/` ไม่ได้ |
| รหัสผิด | audit `login_fail`, นับ failed_logins, ล็อกเมื่อครบ MAX_LOGIN_FAILS |
| admin อนุมัติ | audit `user_approve` → ผู้ใช้ login ได้ · member เปิด /admin → 403 + audit `forbidden_admin` |
| login ผ่าน loopback + header `Tailscale-User-Login` + XFF | ผูก `tailscale_login`, ip ใน log = XFF (IP จริง) |
| client ใหม่ + header เดิม จาก loopback | auto-login (audit `login_tailscale`) |
| header ปลอมจาก IP ที่ไม่ใช่ loopback / header ของคนที่ไม่มีในระบบ | ไม่เชื่อ → redirect ไป login |

ข้อควรระวัง: **ไม่มี CSRF token** (ฟอร์ม POST ทั้งหมด) — ยอมรับได้ในบริบท Tailnet-only + SameSite=Lax แต่ถ้าจะเปิดกว้างขึ้นให้เพิ่ม Flask-WTF CSRF (งานถัดไป ข้อ 9)

---

## 8. สิ่งที่ยังไม่ได้ทดสอบ / ปัญหาที่รู้ (ทำเป็นอย่างแรก)

1. **ยังไม่เคยดึงฟีดจริง** — sandbox ที่สร้างบล็อกเน็ตออก ทดสอบด้วย mock feeds (RSS ×3, หน้าแรกที่มี `<link rel=alternate>`, HTML แบบ Telegram) เท่านั้น → รัน `FLASK_APP=app.py flask fetch` บนเครื่องจริง แล้วดู `/sources` + `/admin/logs?kind=fetch` ไล่แก้แหล่งที่ error: แก้ `feed_url`, เปลี่ยน `fetch_kind` เป็น `gnews`, หรือลบโดเมนที่ไม่มีจริง แล้วอัปเดต `seed_sources.py` ให้ตรง
2. **Google News RSS** เป็น fallback หลักของแหล่งที่ไม่มี RSS — ถ้า Google เริ่มบล็อก/เปลี่ยนรูปแบบ แหล่งจำนวนมากจะพังพร้อมกัน ควรเฝ้าดู; ลิงก์ที่ได้เป็น redirect ผ่าน news.google.com (ยังไม่ resolve เป็น URL ต้นทาง → dedupe ข้ามแหล่งอาจไม่ชนกันแม้เป็นข่าวเดียวกัน แต่ clustering ยังจับกลุ่มให้)
3. **classifier เป็น keyword-based** — precision/recall ยังไม่ได้วัดกับข่าวจริง คาดว่าต้องจูน `DEFAULT_KEYWORDS`/`NOISE_WORDS`/เกณฑ์คะแนน (ตอนนี้ต้อง ≥2 คะแนน = เจอในหัวข้อ 1 คำ) หลังเห็นข่าวจริง 1–2 วัน
4. **clustering ข้ามภาษาไม่ได้** (ข่าวไทยกับข่าวอังกฤษเรื่องเดียวกันเป็นคนละ story) และหัวข้อเดียวกันที่ใช้คำต่างมาก ๆ อาจไม่รวม — threshold 0.38 ปรับที่ `cluster.SIM_THRESHOLD`
5. **Facebook / X / TikTok / Instagram ไม่มี RSS สาธารณะ** — ตอนนี้บัญชีบนแพลตฟอร์มเหล่านี้ถูกแปลงเป็น `gnews_query` (ข่าวที่กล่าวถึงชื่อ/handle) ผู้ใช้อาจคาดหวังโพสต์ตรง → ทางออกคือ RSSHub (`RSSHUB_BASE`) ซึ่งโค้ดรองรับแล้วแต่ยังไม่ได้ทดสอบกับ RSSHub จริง; route ที่ใช้อยู่ใน `views.source_detect` (facebook/page, twitter/user, tiktok/user, picuki/profile)
6. **ไม่มี `title_th`** — โมเดลมีฟิลด์แปลหัวข้ออังกฤษเป็นไทยไว้แล้วแต่ยังไม่มีตัวแปล (ผู้ใช้เคยเห็นใน mockup ว่า "แปลหัวข้อเป็นไทยอัตโนมัติ") — ใส่ Gemini/Google Translate ในขั้น store_items ได้
7. **ticker ใช้ CSS animation ซ้ำเนื้อหา 2 รอบ** — ถ้าข่าวด่วนน้อยกว่า ~4 รายการจะเห็นช่องว่าง
8. **`source_edit` แสดงข่าว 20 รายการล่าสุด** ผ่านตัวแปร `arts` (แก้จากการ query ใน template แล้ว)
9. **หน้า sources โหลด `today_count` ผ่าน dict counts** — โอเค แต่ `Source.today_count()` ที่เหลืออยู่ใน model ยิง query ต่อแถวถ้าใครเรียกใน loop
10. Google Fonts โหลดจากเน็ต — ถ้าต้องการ offline ให้ดาวน์โหลด woff2 มาไว้ใน static/fonts แล้วเปลี่ยน `@import`

---

## 9. งานถัดไปที่เหมาะสม (เรียงตามคุณค่า)

1. รันจริง → ไล่แก้แหล่งที่ error (ข้อ 8.1) → อัปเดต seed
2. จูน classifier/threshold จากข่าวจริง (ข้อ 8.3–8.4) — อาจเพิ่มหน้า admin สำหรับ `Keyword(kind=classify)` และปุ่ม "ไม่ใช่หมวดนี้ / ซ่อนข่าว" (มีฟิลด์ `Article.hidden` รอไว้แล้ว ยังไม่มี UI)
3. แปลหัวข้อต่างประเทศเป็นไทย (`title_th`) ด้วย Gemini (ผู้ใช้ใช้ Gemini อยู่แล้วในงาน LINE OA)
4. เชื่อม LINE จริง: ตั้ง `LINE_CHANNEL_ACCESS_TOKEN`/`LINE_TO` ทดสอบ `flask morning-brief`
5. CSRF (Flask-WTF) + rate limit ที่ /login /register
6. Flask-Migrate สำหรับ schema ต่อไป
7. ตัวเลือก "ซ่อนข่าว / รวม story ด้วยมือ / แยก story" ในหน้า story
8. หน้า mobile: responsive มีแล้ว (≤1200px ยุบเป็นคอลัมน์เดียว) แต่ยังไม่ได้ขัดเกลา

---

## 10. คำสั่งและตัวแปรที่ใช้บ่อย

```bash
# dev (ในเครื่อง, ปิด gate Tailnet, ปิด scheduler)
TAILSCALE_ONLY=0 DISABLE_SCHEDULER=1 FLASK_APP=app.py flask seed
TAILSCALE_ONLY=0 DISABLE_SCHEDULER=1 python app.py          # http://127.0.0.1:8085
TAILSCALE_ONLY=0 DISABLE_SCHEDULER=1 FLASK_APP=app.py flask fetch [--source ID]
FLASK_APP=app.py flask create-admin chuey <pass> --name Chuey
FLASK_APP=app.py flask approve <username>
FLASK_APP=app.py flask morning-brief

# prod
./scripts/install.sh && ./scripts/run.sh && ./scripts/tailscale-serve.sh
```

ตัวแปร `.env` สำคัญ: `SECRET_KEY` · `TAILSCALE_ONLY` (1) · `TRUST_TAILSCALE_HEADERS` (1) · `SESSION_COOKIE_SECURE` (เปิดเมื่อใช้ https ของ tailscale serve) · `EXTRA_TRUSTED_CIDRS` · `REGISTRATION_OPEN` · `FIRST_USER_IS_ADMIN` · `FETCH_INTERVAL_MINUTES` (10) · `FETCH_WORKERS` (8) · `KEEP_ONLY_MATCHED` (1) · `ARTICLE_RETENTION_DAYS` (45) · `RSSHUB_BASE` · `LINE_CHANNEL_ACCESS_TOKEN` · `LINE_TO` · `MORNING_BRIEF_TIME` (06:30) · `DATABASE_URL` (เปลี่ยนเป็น PostgreSQL ได้)

**วิธีทดสอบโดยไม่มีเน็ต** (ที่เคยใช้): เสิร์ฟไฟล์ RSS ปลอมด้วย `python3 -m http.server 9099` แล้วสร้าง Source ชี้ `http://127.0.0.1:9099/feed.xml`; ตั้ง `NO_PROXY=127.0.0.1` ถ้ามี proxy; Flask test client ใช้ `environ_base={"REMOTE_ADDR":"100.64.0.5"}` เพื่อผ่าน gate และ `headers={"Tailscale-User-Login":...}` + `REMOTE_ADDR=127.0.0.1` เพื่อทดสอบ auto-login

---

## 11. ข้อตกลงการเขียนโค้ดในโปรเจกต์นี้

- ข้อความทุกอย่างที่ผู้ใช้เห็น (UI, flash, log detail, คอมเมนต์) เป็น**ภาษาไทย**; ชื่อตัวแปร/ฟังก์ชัน/คีย์ เป็นอังกฤษ
- ทุก action ที่เปลี่ยนสถานะต้องเรียก `audit(action, target, detail, ok)` — ดูชื่อ action ที่มีอยู่ใน views/auth เพื่อคงรูปแบบ (`snake_case`, กริยา_กรรม)
- ห้ามคืน ORM object ออกจาก `run_fetch`/thread — ส่ง id
- เพิ่มชนิดแหล่งใหม่: เพิ่มใน `models.FETCH_KINDS` → `fetcher.resolve_fetch_url` หรือ branch ใน `fetch_source` → เดาใน `views.source_detect` → อธิบายใน `_source_form.html` note
- เพิ่มหมวด/ระดับ: แก้ `models.CATEGORIES`/`LEVELS` + CSS vars `--c-*`/`--l-*` + `classifier.DEFAULT_KEYWORDS`
- ไม่ commit `.env`, `data/`, `logs/` (อยู่ใน .gitignore แล้ว)
