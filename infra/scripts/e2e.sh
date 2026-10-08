#!/usr/bin/env sh
# Runs the Playwright E2E suite in the official Playwright container against a RUNNING production stack.
#
#   docker compose up --build -d && docker compose exec api python -m app.scripts.seed_demo --reset
#   sh infra/scripts/e2e.sh                 # stack on localhost:3000
#   WEB_PORT=3100 sh infra/scripts/e2e.sh   # stack on another port
#
# Service workers need a secure context, so inside the container localhost:$WEB_PORT is forwarded to the host and
# the browser talks to http://localhost (a secure context), never to host.docker.internal directly.
# Login is rate-limited (10 attempts / account / 5 min): wait 5 minutes or `docker compose restart api` between back-to-back runs.
# Reuses the node_modules volumes created by the web-dev service (docker compose -f docker-compose.yml -f docker-compose.dev.yml up web-dev).
set -eu
WEB_PORT="${WEB_PORT:-3000}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
case "$(uname -s)" in MINGW*|MSYS*) ROOT="$(cd "$ROOT" && pwd -W)"; export MSYS_NO_PATHCONV=1 ;; esac
FORWARD="const n=require('net');n.createServer(c=>{const s=n.connect($WEB_PORT,'host.docker.internal');c.pipe(s).pipe(c);s.on('error',()=>c.destroy());c.on('error',()=>s.destroy())}).listen($WEB_PORT,'127.0.0.1')"
exec docker run --rm --ipc=host --add-host=host.docker.internal:host-gateway \
  -e E2E_BASE_URL="http://localhost:$WEB_PORT" -e CI=1 \
  -v "$ROOT:/repo" \
  -v plasticloop_web-node-modules:/repo/node_modules \
  -v plasticloop_web-app-node-modules:/repo/apps/web/node_modules \
  -w /repo/apps/web mcr.microsoft.com/playwright:v1.64.0-noble \
  sh -c "node -e \"$FORWARD\" & sleep 1; npx playwright test --reporter=list $*"
