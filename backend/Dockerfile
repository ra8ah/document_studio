# Backend image for Render / Railway (Docker hosts). NOT for Vercel serverless:
# server PDFs need a long-lived headless Chromium (Playwright).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt \
 # headless-shell Chromium + its OS libraries + fonts (Liberation/DejaVu fallbacks for the footer)
 && playwright install --with-deps --only-shell chromium \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && chmod -R a+rX /ms-playwright

# Unprivileged runtime user (Chromium runs as this user too)
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app

COPY --chown=app:app . .

USER app

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8001'), timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
