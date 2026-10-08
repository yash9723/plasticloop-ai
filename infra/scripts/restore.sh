#!/usr/bin/env sh
# Restores a backup made by backup.sh into the RUNNING stack. This REPLACES the current database and uploads.
#   sh infra/scripts/restore.sh backups/20261009T020000Z
set -eu
case "$(uname -s)" in MINGW*|MSYS*) export MSYS_NO_PATHCONV=1 ;; esac  # Git Bash on Windows
cd "$(dirname "$0")/../.."
DIR="${1:?usage: restore.sh <backup directory>}"
test -s "$DIR/db.dump" || { echo "missing $DIR/db.dump" >&2; exit 1; }
printf 'This replaces the database and uploads of the running stack with %s. Type "restore" to continue: ' "$DIR"
read -r answer
[ "$answer" = "restore" ] || { echo "cancelled"; exit 1; }
docker compose stop worker web >/dev/null
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$DIR/db.dump"
if [ -s "$DIR/uploads.tar.gz" ]; then
  docker compose exec -T api sh -c 'find /data/uploads -mindepth 1 -delete && tar -C /data/uploads -xzf -' < "$DIR/uploads.tar.gz"
fi
docker compose restart api >/dev/null   # re-runs migrations (no-op if current) and rewrites broker credentials
docker compose start worker web >/dev/null
echo "restored from $DIR"
