# Backend deploy image for Railway / Render / Fly.io
# Runs FastAPI + headless Chromium (Playwright) for server-side PDF export.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Python deps (minimal, deploy-only)
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# Chromium + all system libraries it needs (for PDF generation)
RUN playwright install --with-deps chromium

# App code
COPY . .

EXPOSE 8001

# Railway/Render provide $PORT; default to 8001 locally
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
