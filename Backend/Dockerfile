# CIRA backend. Build from the repository root:
#   docker build -t cira-backend ./Backend
FROM python:3.11-slim

# hdbcli ships as a wheel from the SAP HANA Client installer; see requirements.txt.
# Install it in your own image layer if you need direct HANA SQL, otherwise CIRA
# falls back to the Service Layer / reports HANA as unavailable.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl libpq5 unixodbc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || \
    (echo "hdbcli is not on PyPI — installing without it" && \
     grep -v hdbcli requirements.txt > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt)

COPY . .

# Runtime data (cira.db, sandbox, uploads, audit.jsonl) lives here — mount a volume.
RUN useradd -m -u 10001 cira && mkdir -p /app/data && chown -R cira:cira /app
USER cira
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# No --reload, no --root-path surprises: uvicorn behind your reverse proxy.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
