FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r bot
COPY . .
RUN chown -R bot:bot /app
USER bot

# python-based: /health in webhook mode, PID-1 liveness in polling mode
# (slim image has no pgrep/curl)
HEALTHCHECK --interval=30s --timeout=6s --start-period=15s --retries=3 \
    CMD python -m app.healthcheck || exit 1

CMD ["python", "-m", "app.main"]
