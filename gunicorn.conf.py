import os
bind = os.environ.get("BIND", "127.0.0.1:8085")
workers = 1          # ต้อง 1 worker เพราะ scheduler รันในโปรเซสเดียวกัน (ใช้ threads แทน)
threads = 8
timeout = 120
accesslog = None     # ระบบเขียน access log เองที่ logs/access.log
errorlog = "-"
