# Backend image for Railway / Render / Fly.io / Cloud Run / Koyeb.
# Slim: FastAPI + Motor + python-docx only. No Chromium / Playwright —
# PDFs are produced client-side by the browser's print engine.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Unprivileged runtime user
RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY --chown=app:app . .

USER app

EXPOSE 8001

# Same endpoint Render/Railway use (pings MongoDB)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8001'), timeout=4)" || exit 1

# Hosts provide $PORT; default to 8001 locally
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
