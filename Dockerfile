# Auditly command-line crawler in a container (no desktop UI).
#   docker build -t auditly .
#   docker run --rm -v "$PWD/reports:/reports" auditly crawl https://example.com -o /reports -f master_csv,xlsx,html,prompt
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=offscreen XDG_DATA_HOME=/data
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auditly ./auditly
COPY plugins ./plugins
COPY run_auditly.py .
VOLUME ["/reports", "/data"]
ENTRYPOINT ["python", "run_auditly.py"]
CMD ["--help"]
