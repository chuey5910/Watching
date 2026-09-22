"""ส่งข้อความเข้า LINE ผ่าน Messaging API (push) — ปิดใช้งานเองถ้าไม่ได้ตั้ง token"""
import logging
import requests
from flask import current_app

log = logging.getLogger("jabta.line")


def push_text(text: str) -> bool:
    token = current_app.config.get("LINE_CHANNEL_ACCESS_TOKEN")
    to = current_app.config.get("LINE_TO")
    if not token or not to:
        log.debug("LINE ไม่ได้ตั้งค่า ข้าม: %s", text[:60])
        return False
    try:
        r = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"to": to, "messages": [{"type": "text", "text": text[:4900]}]},
            timeout=15,
        )
        if r.status_code >= 300:
            log.warning("LINE push ล้มเหลว %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as ex:
        log.warning("LINE push error: %s", ex)
        return False
