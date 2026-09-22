FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV BIND=0.0.0.0:8085 TZ=Asia/Bangkok
VOLUME ["/app/data", "/app/logs"]
EXPOSE 8085
CMD ["sh", "-c", "FLASK_APP=app.py DISABLE_SCHEDULER=1 flask seed && gunicorn -c gunicorn.conf.py app:app"]
