"""จุดเริ่มต้น: python app.py  (หรือ gunicorn -c gunicorn.conf.py app:app)"""
import os
from jabta import create_app
from jabta import scheduler

app = create_app()
if os.environ.get("DISABLE_SCHEDULER", "").lower() not in ("1", "true"):
    scheduler.start(app)

if __name__ == "__main__":
    # ผูกกับ 127.0.0.1 เท่านั้น แล้วให้ `tailscale serve` เป็นคนเปิดให้ Tailnet
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8085")), debug=False)
