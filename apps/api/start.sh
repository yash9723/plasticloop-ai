#!/bin/sh
# Container entrypoint: migrate, optionally seed synthetic demo data once, then serve.
set -e

alembic upgrade head

# Hosted demo only (SEED_DEMO_ON_START=true). Runs in the background so the port opens immediately. Seeds an empty
# database, does nothing while the stored seed version is current, and reseeds once when SEED_VERSION changes.
# Refuses outright when DEMO_MODE is off or ENVIRONMENT=production.
if [ "$SEED_DEMO_ON_START" = "true" ]; then
    (python -m app.scripts.seed_demo --if-outdated || true) &
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 5
