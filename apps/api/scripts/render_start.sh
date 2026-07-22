#!/usr/bin/env sh
set -eu

: "${DJANGO_SECRET_KEY:?DJANGO_SECRET_KEY is required}"

# Render can generate a strong random Django secret automatically. Derive a
# valid Fernet key from it so the demo deploy needs no manually pasted secret.
if [ -z "${MFA_ENCRYPTION_KEY:-}" ]; then
  MFA_ENCRYPTION_KEY="$(python - <<'PY'
import base64
import hashlib
import os

secret = os.environ["DJANGO_SECRET_KEY"].encode("utf-8")
print(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()).decode("ascii"))
PY
)"
  export MFA_ENCRYPTION_KEY
fi

python manage.py migrate --noinput
python manage.py seed_demo

exec uvicorn config.asgi:application \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
