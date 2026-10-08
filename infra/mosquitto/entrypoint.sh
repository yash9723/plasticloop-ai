#!/bin/sh
# Starts Mosquitto and hot-reloads credentials whenever the API rewrites the shared passwd file.
# The API owns the source of truth (device_credentials table); this script only mirrors it.
set -eu

SRC=/mosquitto/auth/passwd
RUN=/mosquitto/runtime

mkdir -p "$RUN" /mosquitto/data
chown -R mosquitto:mosquitto /mosquitto/data

sync_files() {
  if [ -f "$SRC" ]; then cp "$SRC" "$RUN/passwd"; else : > "$RUN/passwd"; fi
  cp /plasticloop/acl "$RUN/acl"
  chown mosquitto:mosquitto "$RUN/passwd" "$RUN/acl"
  chmod 0600 "$RUN/passwd" "$RUN/acl"
}

digest() {
  if [ -f "$SRC" ]; then md5sum "$SRC" | cut -d' ' -f1; else echo none; fi
}

sync_files
mosquitto -c /plasticloop/mosquitto.conf &
PID=$!
trap 'kill -TERM "$PID" 2>/dev/null; wait "$PID"; exit 0' TERM INT

LAST=$(digest)
while kill -0 "$PID" 2>/dev/null; do
  sleep 3 &
  wait $!
  NOW=$(digest)
  if [ "$NOW" != "$LAST" ]; then
    sync_files
    kill -HUP "$PID"
    LAST=$NOW
    echo "plasticloop: credentials changed, mosquitto reloaded"
  fi
done
wait "$PID"
