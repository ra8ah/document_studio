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

# Hosts provide $PORT; default to 8001 locally
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
