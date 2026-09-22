#!/usr/bin/env bash
# รันแบบ production ด้วย gunicorn (1 worker หลาย thread — scheduler อยู่ในโปรเซสเดียวกัน)
cd "$(dirname "$0")/.."
. .venv/bin/activate
exec gunicorn -c gunicorn.conf.py app:app
