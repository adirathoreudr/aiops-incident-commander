# executor/Dockerfile
# Multi-stage Python build — Kubernetes client + ArgoCD REST

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/sh --create-home appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup . .

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/healthz')"

EXPOSE 8002

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    IN_CLUSTER=true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", \
     "--workers", "1", "--loop", "uvloop"]
