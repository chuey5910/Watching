#!/usr/bin/env bash
# เปิดให้เครื่องอื่นใน Tailnet เข้าถึงผ่าน HTTPS ที่ https://<ชื่อเครื่อง>.<tailnet>.ts.net
# tailscale serve จะ proxy มาที่ 127.0.0.1:8085 พร้อมใส่ header Tailscale-User-Login ให้ระบบล็อกอินอัตโนมัติ
set -e
PORT="${PORT:-8085}"
tailscale serve --bg --https=443 "http://127.0.0.1:${PORT}"
echo
tailscale serve status
echo
echo "URL สำหรับเข้าใช้:  https://$(tailscale status --json | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["Self"]["DNSName"].rstrip("."))')"
echo "ปิดการแชร์:        tailscale serve reset"
