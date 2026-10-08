#!/usr/bin/env sh
# Backs up the PostgreSQL database and uploaded files of a running stack.
#   sh infra/scripts/backup.sh                       -> backups/<UTC timestamp>/{db.dump,uploads.tar.gz}
#   COMPOSE_PROJECT_NAME=plasticloop sh infra/scripts/backup.sh
# Broker credentials are not backed up: the API rebuilds them from the database on start.
# Keep backups off the server (e.g. rclone to object storage) and test restores regularly.
set -eu
case "$(uname -s)" in MINGW*|MSYS*) export MSYS_NO_PATHCONV=1 ;; esac  # Git Bash on Windows
cd "$(dirname "$0")/../.."
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/$STAMP"
mkdir -p "$OUT"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$OUT/db.dump"
docker compose exec -T api tar -C /data/uploads -czf - . > "$OUT/uploads.tar.gz"
test -s "$OUT/db.dump" || { echo "database dump is empty" >&2; exit 1; }
echo "backup written to $OUT ($(du -sh "$OUT" | cut -f1))"
