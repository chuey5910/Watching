"""Tailscale gate, การระบุ IP ที่แท้จริง และ audit log"""
import ipaddress
import logging
from functools import wraps

from flask import request, abort, current_app, g
from flask_login import current_user

from .models import db, AuditLog

log = logging.getLogger("jabta.security")
audit_file_log = logging.getLogger("jabta.audit")

TAILNET = ipaddress.ip_network("100.64.0.0/10")
TAILNET6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
LOOPBACKS = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]


def client_ip() -> str:
    """IP ผู้ใช้จริง — `tailscale serve` จะ proxy มาจาก 127.0.0.1 และใส่ X-Forwarded-For ให้"""
    remote = request.remote_addr or "0.0.0.0"
    try:
        r = ipaddress.ip_address(remote)
    except ValueError:
        return remote
    if any(r in n for n in LOOPBACKS):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return remote


def is_from_loopback() -> bool:
    try:
        return any(ipaddress.ip_address(request.remote_addr) in n for n in LOOPBACKS)
    except Exception:
        return False


def is_trusted_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a in TAILNET or a in TAILNET6 or any(a in n for n in LOOPBACKS):
        return True
    for cidr in current_app.config.get("EXTRA_TRUSTED_CIDRS", []):
        try:
            if a in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def tailscale_identity():
    """คืน (login, name) จาก header ที่ tailscale serve ใส่ให้ — เชื่อเฉพาะเมื่อมาจาก loopback"""
    if not current_app.config.get("TRUST_TAILSCALE_HEADERS"):
        return None, None
    if not is_from_loopback():
        return None, None
    login = request.headers.get("Tailscale-User-Login")
    name = request.headers.get("Tailscale-User-Name")
    return (login or None), (name or None)


def enforce_tailscale_gate():
    """before_request: ปฏิเสธทุกคำขอที่ไม่ได้มาจาก Tailnet (เมื่อ TAILSCALE_ONLY เปิด)"""
    if not current_app.config.get("TAILSCALE_ONLY"):
        return None
    if request.path.startswith("/static/"):
        return None
    ip = client_ip()
    g.client_ip = ip
    if not is_trusted_ip(ip):
        log.warning("ปฏิเสธคำขอจากนอก Tailnet ip=%s path=%s", ip, request.path)
        audit("blocked_ip", target=request.path, detail=f"ip {ip} ไม่อยู่ใน Tailnet", ok=False, commit=True)
        abort(403)
    return None


def audit(action: str, target: str = "", detail: str = "", ok: bool = True, user=None, commit: bool = True):
    """บันทึกเหตุการณ์ลงตาราง audit_logs และไฟล์ logs/audit.log"""
    try:
        u = user if user is not None else (current_user if current_user and current_user.is_authenticated else None)
    except Exception:
        u = None
    ts_login, _ = tailscale_identity()
    entry = AuditLog(
        user_id=getattr(u, "id", None),
        username=getattr(u, "username", None),
        action=action,
        target=(target or "")[:200],
        detail=detail,
        ip=client_ip() if request else None,
        tailscale_login=ts_login,
        user_agent=(request.headers.get("User-Agent", "")[:300] if request else None),
        ok=ok,
    )
    db.session.add(entry)
    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    audit_file_log.info(
        "%s user=%s ip=%s ts=%s target=%s ok=%s %s",
        action, entry.username or "-", entry.ip or "-", ts_login or "-", entry.target or "-", ok, (detail or "").replace("\n", " ")[:300],
    )


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated or not current_user.is_admin:
            audit("forbidden_admin", target=request.path, ok=False)
            abort(403)
        return f(*a, **kw)
    return wrapper
