# ScanScribe — multi-stage: compile wheels in builder, slim runtime with non-root user
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- runtime (repeat ARG so FROM can use PYTHON_VERSION) ---
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="ScanScribe"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config.yml \
    MODEL_PATH=/app/models \
    INGEST_DIR=/app/ingest \
    OUTPUT_DIR=/app/audio_storage \
    LOG_DIR=/app/logs

RUN mkdir -p /app/ingest /app/audio_storage /app/logs /app/models \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser app/ /app/app/
# Default config (override with bind mount or CONFIG_PATH)
COPY --chown=appuser:appuser config.yml.example /app/config.yml

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
