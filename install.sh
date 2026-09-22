#!/usr/bin/env bash
# ติดตั้งครั้งแรก: สร้าง venv, ติดตั้งไลบรารี, สร้าง .env, สร้างฐานข้อมูล + รายชื่อสื่อเริ่มต้น
set -e
cd "$(dirname "$0")/.."
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip -q
pip install -r requirements.txt -q
[ -f .env ] || { cp .env.example .env; sed -i.bak "s/^SECRET_KEY=.*/SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')/" .env && rm -f .env.bak; echo "สร้าง .env แล้ว (แก้ค่าเพิ่มเติมได้)"; }
mkdir -p data logs
FLASK_APP=app.py DISABLE_SCHEDULER=1 flask seed
echo
echo "ติดตั้งเสร็จ ▶ เริ่มใช้งาน:  ./scripts/run.sh   แล้วเปิดเบราว์เซอร์ที่ http://127.0.0.1:8085 เพื่อสร้างบัญชี admin คนแรก"
echo "เปิดให้ Tailnet เข้าถึง:       ./scripts/tailscale-serve.sh"
