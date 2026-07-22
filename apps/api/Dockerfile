FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_CONCURRENCY=2

RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
