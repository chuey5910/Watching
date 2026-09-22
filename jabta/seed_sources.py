"""รายชื่อสื่อเริ่มต้น (แก้ไข/เพิ่มได้ในหน้า "แหล่งข่าว")
kind: rss = ลอง RSS ก่อน (ถ้าพังจะค้นหาเอง แล้ว fallback เป็น Google News site:โดเมน) · gnews = ใช้ Google News site: ตั้งแต่แรก"""
from .models import db, Source, Rule, Keyword

ALL = "politics,governance,hardship,disaster,protest"


def S(name, t, home, feed=None, kind="rss", region="ทั่วประเทศ", country="ไทย", lang="th", **kw):
    return dict(name=name, source_type=t, homepage=home, feed_url=feed, fetch_kind=kind, region=region,
                country=country, language=lang, categories=ALL, **kw)


MAINSTREAM = [
    S("ไทยพีบีเอส", "mainstream", "https://www.thaipbs.or.th", kind="gnews", priority=3,
      alert_categories="disaster,protest"),
    S("สำนักข่าวไทย (อสมท.)", "mainstream", "https://tna.mcot.net", kind="gnews", priority=2),
    S("สำนักข่าวกรมประชาสัมพันธ์ (NNT)", "government", "https://thainews.prd.go.th", kind="gnews", priority=2),
    S("ไทยรัฐออนไลน์", "mainstream", "https://www.thairath.co.th", "https://www.thairath.co.th/rss/news", priority=3),
    S("ข่าวสด", "mainstream", "https://www.khaosod.co.th", "https://www.khaosod.co.th/feed", priority=2),
    S("มติชนออนไลน์", "mainstream", "https://www.matichon.co.th", "https://www.matichon.co.th/feed", priority=3),
    S("เดลินิวส์", "mainstream", "https://www.dailynews.co.th", "https://www.dailynews.co.th/news/feed", priority=2),
    S("คมชัดลึก", "mainstream", "https://www.komchadluek.net", kind="gnews"),
    S("แนวหน้า", "mainstream", "https://www.naewna.com", kind="gnews"),
    S("ผู้จัดการออนไลน์", "mainstream", "https://mgronline.com", "https://mgronline.com/rss/politics.xml", priority=2),
    S("โพสต์ทูเดย์", "mainstream", "https://www.posttoday.com", kind="gnews"),
    S("ไทยโพสต์", "mainstream", "https://www.thaipost.net", kind="gnews"),
    S("บ้านเมือง", "mainstream", "https://www.banmuang.co.th", kind="gnews"),
    S("สยามรัฐ", "mainstream", "https://siamrath.co.th", kind="gnews"),
    S("ช่อง 3 (CH3Plus)", "mainstream", "https://ch3plus.com", kind="gnews"),
    S("ช่อง 7HD", "mainstream", "https://news.ch7.com", kind="gnews"),
    S("อมรินทร์ทีวี", "mainstream", "https://www.amarintv.com", kind="gnews"),
    S("ไทยรัฐทีวี", "mainstream", "https://www.thairath.co.th/tv", kind="gnews"),
    S("PPTV", "mainstream", "https://www.pptvhd36.com", kind="gnews"),
    S("เนชั่นทีวี", "mainstream", "https://www.nationtv.tv", kind="gnews"),
    S("TNN", "mainstream", "https://www.tnnthailand.com", kind="gnews"),
    S("ONE31", "mainstream", "https://www.one31.net", kind="gnews"),
    S("Workpoint News", "mainstream", "https://workpointtoday.com", "https://workpointtoday.com/feed/"),
    S("ช่อง 8", "mainstream", "https://www.thaich8.com", kind="gnews"),
    S("MONO29", "mainstream", "https://mono29.com", kind="gnews"),
    S("ประชาชาติธุรกิจ", "mainstream", "https://www.prachachat.net", "https://www.prachachat.net/feed", priority=2),
    S("กรุงเทพธุรกิจ", "mainstream", "https://www.bangkokbiznews.com", kind="gnews", priority=2),
    S("ฐานเศรษฐกิจ", "mainstream", "https://www.thansettakij.com", kind="gnews"),
    S("The Standard", "mainstream", "https://thestandard.co", "https://thestandard.co/feed/", priority=2),
    S("Thairath Plus", "mainstream", "https://plus.thairath.co.th", kind="gnews"),
    S("ประชาไท", "mainstream", "https://prachatai.com", "https://prachatai.com/rss.xml", priority=3, alert_categories="protest"),
    S("The Momentum", "mainstream", "https://themomentum.co", "https://themomentum.co/feed/"),
    S("The Matter", "mainstream", "https://thematter.co", "https://thematter.co/feed"),
    S("The Reporters", "mainstream", "https://www.thereporters.co", kind="gnews", priority=2),
    S("iLaw", "mainstream", "https://www.ilaw.or.th", kind="gnews", priority=2),
    S("สำนักข่าวอิศรา", "mainstream", "https://www.isranews.org", kind="gnews", priority=2),
    S("Way Magazine", "mainstream", "https://waymagazine.org", "https://waymagazine.org/feed/"),
    S("Voice Online", "mainstream", "https://voicetv.co.th", kind="gnews"),
    S("101.world", "mainstream", "https://www.the101.world", "https://www.the101.world/feed/"),
    S("สำนักข่าวชายขอบ", "local", "https://transbordernews.in.th", "https://transbordernews.in.th/home/feed/", region="ชายแดน", priority=2),
    S("Bangkok Post", "mainstream", "https://www.bangkokpost.com", "https://www.bangkokpost.com/rss/data/topstories.xml", lang="en", priority=2),
    S("The Nation Thailand", "mainstream", "https://www.nationthailand.com", kind="gnews", lang="en"),
    S("Khaosod English", "mainstream", "https://www.khaosodenglish.com", "https://www.khaosodenglish.com/feed/", lang="en"),
    S("Thai Enquirer", "mainstream", "https://www.thaienquirer.com", "https://www.thaienquirer.com/feed/", lang="en"),
]

GOVERNMENT = [
    S("กรมป้องกันและบรรเทาสาธารณภัย (ปภ.)", "government", "https://www.disaster.go.th", kind="gnews", priority=3,
      alert_categories="disaster", keep_all=True),
    S("กรมอุตุนิยมวิทยา", "government", "https://www.tmd.go.th", kind="gnews", priority=3, alert_categories="disaster", keep_all=True),
    S("ศูนย์เตือนภัยพิบัติแห่งชาติ", "government", "https://ndwc.disaster.go.th", kind="gnews", priority=3, keep_all=True),
    S("สำนักงานทรัพยากรน้ำแห่งชาติ (สทนช.)", "government", "https://www.onwr.go.th", kind="gnews", keep_all=True),
    S("กรมชลประทาน", "government", "https://www.rid.go.th", kind="gnews", keep_all=True),
    S("Air4Thai (คุณภาพอากาศ)", "government", "http://air4thai.pcd.go.th", kind="gnews", keep_all=True),
    S("รัฐสภา / สภาผู้แทนราษฎร", "government", "https://www.parliament.go.th", kind="gnews", priority=2),
    S("สำนักงานคณะกรรมการการเลือกตั้ง (กกต.)", "government", "https://www.ect.go.th", kind="gnews", priority=2),
    S("ศาลรัฐธรรมนูญ", "government", "https://www.constitutionalcourt.or.th", kind="gnews", priority=2),
    S("ไทยคู่ฟ้า (ทำเนียบรัฐบาล)", "government", "https://www.thaigov.go.th", kind="gnews", priority=2),
    S("กระทรวงมหาดไทย", "government", "https://www.moi.go.th", kind="gnews", priority=2),
    S("สำนักงานตำรวจแห่งชาติ", "government", "https://www.royalthaipolice.go.th", kind="gnews", priority=2),
]

LOCAL = [
    # ภาคเหนือ
    S("เชียงใหม่นิวส์", "local", "https://www.chiangmainews.co.th", "https://www.chiangmainews.co.th/feed/", region="เชียงใหม่"),
    S("Chiang Mai One", "local", "https://www.chiangmaione.com", kind="gnews", region="เชียงใหม่"),
    S("เชียงรายโฟกัส", "local", "https://www.chiangraifocus.com", kind="gnews", region="เชียงราย", alert_categories="disaster"),
    S("สำนักข่าวลานนา", "local", "https://lannanews.com", kind="gnews", region="ภาคเหนือ"),
    S("Lanner", "local", "https://www.lannernews.com", "https://www.lannernews.com/feed/", region="ภาคเหนือ", priority=2),
    S("CM108 ข่าวเชียงใหม่", "local", "https://www.cm108.com", kind="gnews", region="เชียงใหม่"),
    S("พะเยาทีวี", "local", "https://phayaotv.com", kind="gnews", region="พะเยา"),
    S("แพร่นิวส์", "local", "https://www.phraenews.com", kind="gnews", region="แพร่"),
    S("น่านนิวส์", "local", "https://www.nannews.co", kind="gnews", region="น่าน"),
    S("ตากนิวส์ / แม่สอด", "local", "https://www.taknews.com", kind="gnews", region="ตาก"),
    # อีสาน
    S("อีสานบิซ", "local", "https://www.esanbiz.com", "https://www.esanbiz.com/feed", region="อีสาน"),
    S("The Isaan Record", "local", "https://theisaanrecord.co", "https://theisaanrecord.co/feed/", region="อีสาน", priority=2),
    S("Khon Kaen Link", "local", "https://www.khonkaenlink.info", kind="gnews", region="ขอนแก่น"),
    S("โคราชเดลี่", "local", "https://www.koratdaily.com", kind="gnews", region="นครราชสีมา"),
    S("อุดรนิวส์", "local", "https://www.udonnews.com", kind="gnews", region="อุดรธานี"),
    S("อุบลนิวส์", "local", "https://www.ubonnews.com", kind="gnews", region="อุบลราชธานี"),
    S("สกลนิวส์", "local", "https://www.sakonnews.com", kind="gnews", region="สกลนคร"),
    S("บุรีรัมย์ไทม์", "local", "https://www.buriramtimes.com", kind="gnews", region="บุรีรัมย์"),
    S("หนองคายนิวส์", "local", "https://www.nongkhainews.com", kind="gnews", region="หนองคาย"),
    # กลาง / ตะวันออก / ตะวันตก
    S("ปทุมธานีนิวส์", "local", "https://www.pathumthaninews.com", kind="gnews", region="ปทุมธานี"),
    S("สุพรรณนิวส์", "local", "https://www.suphannews.com", kind="gnews", region="สุพรรณบุรี"),
    S("อยุธยานิวส์", "local", "https://www.ayutthayanews.com", kind="gnews", region="พระนครศรีอยุธยา"),
    S("ชลบุรีนิวส์ / พัทยานิวส์", "local", "https://www.pattayanews.com", kind="gnews", region="ชลบุรี"),
    S("The Pattaya News", "local", "https://thepattayanews.com", "https://thepattayanews.com/feed/", region="ชลบุรี", lang="en"),
    S("ระยองนิวส์", "local", "https://www.rayongnews.com", kind="gnews", region="ระยอง"),
    S("จันท์นิวส์", "local", "https://www.chantnews.com", kind="gnews", region="จันทบุรี"),
    S("กาญจน์นิวส์", "local", "https://www.kannews.com", kind="gnews", region="กาญจนบุรี"),
    S("เพชรบุรีนิวส์", "local", "https://www.phetchaburinews.com", kind="gnews", region="เพชรบุรี"),
    S("ราชบุรีนิวส์", "local", "https://www.ratchaburinews.com", kind="gnews", region="ราชบุรี"),
    # ใต้
    S("สงขลาโฟกัส", "local", "https://www.songkhlafocus.com", kind="gnews", region="สงขลา", priority=2),
    S("The Phuket News", "local", "https://www.thephuketnews.com", kind="gnews", region="ภูเก็ต", lang="en"),
    S("ภูเก็ตนิวส์", "local", "https://www.phuketnews.co.th", kind="gnews", region="ภูเก็ต"),
    S("สำนักข่าวภาคใต้ (South Thailand News)", "local", "https://www.southnews.co.th", kind="gnews", region="ภาคใต้"),
    S("หาดใหญ่โฟกัส", "local", "https://www.hatyaifocus.com", kind="gnews", region="สงขลา"),
    S("Wartani", "local", "https://wartani.com", kind="gnews", region="ชายแดนใต้", priority=2),
    S("The Motive", "local", "https://themotive.co", kind="gnews", region="ชายแดนใต้", priority=2),
    S("Deep South Watch", "local", "https://deepsouthwatch.org", kind="gnews", region="ชายแดนใต้", priority=2),
    S("สำนักข่าวอามาน", "local", "https://www.amannews.co", kind="gnews", region="ชายแดนใต้"),
    S("สุราษฎร์นิวส์", "local", "https://www.suratnews.com", kind="gnews", region="สุราษฎร์ธานี"),
    S("นครนิวส์", "local", "https://www.nakhonnews.com", kind="gnews", region="นครศรีธรรมราช"),
    S("ตรังนิวส์", "local", "https://www.trangnews.com", kind="gnews", region="ตรัง"),
    S("กระบี่นิวส์", "local", "https://www.krabinews.com", kind="gnews", region="กระบี่"),
    # เครือข่ายท้องถิ่นระดับประเทศ
    S("77 ข่าวเด็ด", "local", "https://www.77kaoded.com", kind="gnews", region="ทุกจังหวัด", priority=3),
    S("สยามรัฐ ภูมิภาค", "local", "https://siamrath.co.th/regional", kind="gnews", region="ทุกจังหวัด"),
    S("เนชั่นออนไลน์ ภูมิภาค", "local", "https://www.nationtv.tv/news/region", kind="gnews", region="ทุกจังหวัด"),
    S("ไทยพีบีเอส นักข่าวพลเมือง", "local", "https://thecitizen.plus", kind="gnews", region="ทุกจังหวัด", priority=2),
    S("สำนักข่าว กปส. ภูมิภาค (สปข.)", "government", "https://region1.prd.go.th", kind="gnews", region="ทุกจังหวัด"),
]

FOREIGN = [
    # สำนักข่าวโลก — ดึงเฉพาะที่เกี่ยวข้องกับไทย/ภูมิภาคผ่าน Google News query
    S("Reuters — Thailand", "foreign", "https://www.reuters.com", "Thailand site:reuters.com", kind="gnews_query", country="โลก", lang="en", priority=3),
    S("AP News — Thailand", "foreign", "https://apnews.com", "Thailand site:apnews.com", kind="gnews_query", country="โลก", lang="en", priority=2),
    S("AFP (via France24) — Thailand", "foreign", "https://www.france24.com", "Thailand site:france24.com", kind="gnews_query", country="โลก", lang="en"),
    S("Bloomberg — Thailand", "foreign", "https://www.bloomberg.com", "Thailand site:bloomberg.com", kind="gnews_query", country="โลก", lang="en"),
    S("BBC Thai", "foreign", "https://www.bbc.com/thai", "https://feeds.bbci.co.uk/thai/rss.xml", country="สหราชอาณาจักร", priority=3),
    S("BBC World — Asia", "foreign", "https://www.bbc.com/news/world/asia", "https://feeds.bbci.co.uk/news/world/asia/rss.xml", country="สหราชอาณาจักร", lang="en"),
    S("CNN — Thailand", "foreign", "https://edition.cnn.com", "Thailand site:cnn.com", kind="gnews_query", country="สหรัฐฯ", lang="en"),
    S("Al Jazeera — Asia Pacific", "foreign", "https://www.aljazeera.com", "https://www.aljazeera.com/xml/rss/all.xml", country="กาตาร์", lang="en"),
    S("DW — Thailand", "foreign", "https://www.dw.com", "Thailand site:dw.com", kind="gnews_query", country="เยอรมนี", lang="en"),
    S("The Guardian — Thailand", "foreign", "https://www.theguardian.com/world/thailand", "https://www.theguardian.com/world/thailand/rss", country="สหราชอาณาจักร", lang="en"),
    S("The New York Times — Asia Pacific", "foreign", "https://www.nytimes.com", "https://rss.nytimes.com/services/xml/rss/nyt/AsiaPacific.xml", country="สหรัฐฯ", lang="en"),
    S("Washington Post — Thailand", "foreign", "https://www.washingtonpost.com", "Thailand site:washingtonpost.com", kind="gnews_query", country="สหรัฐฯ", lang="en"),
    S("Financial Times — Thailand", "foreign", "https://www.ft.com", "Thailand site:ft.com", kind="gnews_query", country="สหราชอาณาจักร", lang="en"),
    S("The Economist — Thailand", "foreign", "https://www.economist.com", "Thailand site:economist.com", kind="gnews_query", country="สหราชอาณาจักร", lang="en"),
    # เอเชีย/อาเซียน
    S("Nikkei Asia", "foreign", "https://asia.nikkei.com", "Thailand site:asia.nikkei.com", kind="gnews_query", country="ญี่ปุ่น", lang="en", priority=2),
    S("South China Morning Post — Asia", "foreign", "https://www.scmp.com", "https://www.scmp.com/rss/3/feed", country="ฮ่องกง", lang="en"),
    S("The Diplomat", "foreign", "https://thediplomat.com", "https://thediplomat.com/feed/", country="สหรัฐฯ", lang="en"),
    S("Channel NewsAsia (CNA)", "foreign", "https://www.channelnewsasia.com", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511", country="สิงคโปร์", lang="en", priority=2),
    S("The Straits Times — Asia", "foreign", "https://www.straitstimes.com", "https://www.straitstimes.com/news/asia/rss.xml", country="สิงคโปร์", lang="en"),
    S("Asia Times", "foreign", "https://asiatimes.com", "https://asiatimes.com/feed/", country="ฮ่องกง", lang="en"),
    S("Benar News (ไทย)", "foreign", "https://www.benarnews.org/thai", kind="gnews", country="สหรัฐฯ", priority=2),
    S("Radio Free Asia", "foreign", "https://www.rfa.org", "Thailand OR Myanmar site:rfa.org", kind="gnews_query", country="สหรัฐฯ", lang="en"),
    S("VOA Thai", "foreign", "https://www.voathai.com", kind="gnews", country="สหรัฐฯ"),
    # เมียนมา / ชายแดน
    S("The Irrawaddy", "foreign", "https://www.irrawaddy.com", "https://www.irrawaddy.com/feed", country="เมียนมา", lang="en", priority=3, alert_categories="protest,disaster"),
    S("Myanmar Now", "foreign", "https://myanmar-now.org", "https://myanmar-now.org/en/feed/", country="เมียนมา", lang="en", priority=2),
    S("Mizzima", "foreign", "https://eng.mizzima.com", kind="gnews", country="เมียนมา", lang="en"),
    S("DVB", "foreign", "https://english.dvb.no", "https://english.dvb.no/feed", country="เมียนมา", lang="en"),
    S("Frontier Myanmar", "foreign", "https://www.frontiermyanmar.net", kind="gnews", country="เมียนมา", lang="en"),
    S("Karen News", "foreign", "https://karennews.org", "https://karennews.org/feed/", country="เมียนมา", lang="en", priority=2),
    S("Shan Herald (SHAN)", "foreign", "https://english.shannews.org", "https://english.shannews.org/feed/", country="เมียนมา", lang="en"),
    S("BNI Multimedia", "foreign", "https://www.bnionline.net", "https://www.bnionline.net/en/rss.xml", country="เมียนมา", lang="en"),
    # เพื่อนบ้าน
    S("Vientiane Times", "foreign", "https://www.vientianetimes.org.la", kind="gnews", country="ลาว", lang="en"),
    S("The Laotian Times", "foreign", "https://laotiantimes.com", "https://laotiantimes.com/feed/", country="ลาว", lang="en"),
    S("Khmer Times", "foreign", "https://www.khmertimeskh.com", "https://www.khmertimeskh.com/feed/", country="กัมพูชา", lang="en"),
    S("CamboJA News", "foreign", "https://cambojanews.com", "https://cambojanews.com/feed/", country="กัมพูชา", lang="en"),
    S("Bernama", "foreign", "https://www.bernama.com", kind="gnews", country="มาเลเซีย", lang="en"),
    S("Malay Mail", "foreign", "https://www.malaymail.com", "https://www.malaymail.com/feed/rss/malaysia", country="มาเลเซีย", lang="en"),
    S("Free Malaysia Today", "foreign", "https://www.freemalaysiatoday.com", "https://www.freemalaysiatoday.com/feed/", country="มาเลเซีย", lang="en"),
    S("VnExpress International", "foreign", "https://e.vnexpress.net", "https://e.vnexpress.net/rss/news.rss", country="เวียดนาม", lang="en"),
    S("Tuoi Tre News", "foreign", "https://tuoitrenews.vn", "https://tuoitrenews.vn/rss/", country="เวียดนาม", lang="en"),
    # ภัยพิบัติระดับภูมิภาค
    S("ReliefWeb — Thailand", "foreign", "https://reliefweb.int/country/tha", "https://reliefweb.int/updates/rss.xml?advanced-search=%28C226%29", country="UN", lang="en", keep_all=True, priority=2),
    S("GDACS (แจ้งเตือนภัยพิบัติโลก)", "foreign", "https://www.gdacs.org", "https://www.gdacs.org/xml/rss.xml", country="EU/UN", lang="en", keep_all=True, alert_categories="disaster"),
    S("USGS Earthquakes M4.5+", "foreign", "https://earthquake.usgs.gov", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.atom", country="สหรัฐฯ", lang="en", keep_all=True),
    S("AHA Centre (ASEAN)", "foreign", "https://ahacentre.org", "https://ahacentre.org/feed/", country="อาเซียน", lang="en", keep_all=True),
    S("Japan Meteorological Agency — typhoon", "foreign", "https://www.jma.go.jp", "typhoon site:jma.go.jp OR site:tropic.ssec.wisc.edu", kind="gnews_query", country="ญี่ปุ่น", lang="en", keep_all=True),
]

DEFAULT_RULES = [
    dict(name="ภัยพิบัติที่มี ≥3 แหล่งรายงานใน 1 ชม. → ปักหมุด (จำเป็น)", category="disaster", min_sources=3, within_hours=1,
         action="pin", set_level="essential", notify_line=True),
    dict(name="ชุมนุม: บัญชีกลุ่ม 'ผู้นำการชุมนุม' โพสต์คำนัดหมาย → ปักหมุด + แจ้ง LINE", category="protest", min_sources=1,
         within_hours=6, keywords="นัดหมาย,รวมตัว,เคลื่อนขบวน,นัดรวมพล,ปิดถนน", source_type="social", source_group="ผู้นำการชุมนุม",
         action="pin", set_level="important", notify_line=True),
    dict(name="ประกาศจากหน่วยงานรัฐ: เขตภัยพิบัติ/ฉุกเฉิน/เคอร์ฟิว → ปักหมุดอันดับ 1", category=None, min_sources=1, within_hours=3,
         keywords="ประกาศเขต,ภาวะฉุกเฉิน,เคอร์ฟิว,กฎอัยการศึก,พื้นที่ประสบภัย", source_type="government", action="pin_top",
         set_level="essential", notify_line=True, enabled=False),
    dict(name="การเมืองใหญ่: ≥8 แหล่งใน 3 ชม. → ติดระดับ 'สำคัญ'", category="politics", min_sources=8, within_hours=3,
         action="flag", set_level="important"),
]

DEFAULT_WATCH = ["เหมืองแร่", "ไล่รื้อ", "ปิดถนน", "ค่าไฟ", "ราคาข้าว", "ชายแดน", "อภิปรายไม่ไว้วางใจ", "ยุบสภา"]


# ฟิลด์ที่ --update ยอมเขียนทับของเดิม — จำกัดไว้เท่าที่จำเป็นต่อการดึงข่าว
# ไม่แตะ enabled/categories/alert_* เพราะผู้ใช้อาจปรับเองผ่านหน้าเว็บไปแล้ว
SYNC_FIELDS = ("feed_url", "fetch_kind", "homepage")


def seed(reset: bool = False, update: bool = False) -> int:
    """update=True จะซิงก์ URL/ชนิดการดึงของแหล่งที่มีอยู่แล้วให้ตรงกับไฟล์นี้

    จำเป็นเพราะปกติ seed ข้ามแหล่งที่ชื่อซ้ำ การแก้ URL ในไฟล์นี้จึงไม่มีผล
    กับฐานข้อมูลที่ seed ไปแล้ว
    """
    if reset:
        Source.query.delete()
    by_name = {s.name: s for s in Source.query.all()}
    n = 0
    for d in MAINSTREAM + GOVERNMENT + LOCAL + FOREIGN:
        cur = by_name.get(d["name"])
        if cur is not None:
            if update:
                changed = []
                for f in SYNC_FIELDS:
                    want = d.get(f)
                    if getattr(cur, f) != want:
                        changed.append(f"{f}: {getattr(cur, f)} -> {want}")
                        setattr(cur, f, want)
                if changed:
                    # ล้างผลการค้นหา feed รอบเก่า ไม่งั้นจะยังดึงจาก URL เดิมที่พังอยู่
                    cur.resolved_feed_url = None
                    cur.etag = cur.modified = None
                    cur.last_status, cur.last_error = "new", None
                    print(f"  [{cur.id}] {cur.name}: " + " | ".join(changed))
                    n += 1
            continue
        db.session.add(Source(**d))
        n += 1
    if Rule.query.count() == 0:
        for r in DEFAULT_RULES:
            db.session.add(Rule(**r))
    if Keyword.query.filter_by(kind="watch").count() == 0:
        for w in DEFAULT_WATCH:
            db.session.add(Keyword(word=w, kind="watch"))
    db.session.commit()
    return n
