FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/stefanhoagland/soundbendingsecuencias" \
      org.opencontainers.image.description="Soundbending Secuencias multitrack library server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SBS_DATA_DIR=/data \
    HF_HOME=/data/models/hf \
    PORT=8080

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Unraid's default "nobody:users" is 99:100; override with PUID/PGID-style --user if you like.
RUN mkdir -p /data && chown 99:100 /data
USER 99:100
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/healthz')" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
