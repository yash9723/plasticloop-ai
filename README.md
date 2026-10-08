# PlasticLoop AI

Rural plastic-waste collection, traceability and resource recovery for Gram Panchayats and MRF / PWMU operators
(SIH 2026 problem statement **SIH26259**: management of multilayer plastic (MLP) at PWMU / MRF level).

Households → collection points (QR) → collectors (offline-first PWA) → optimised vehicle routes → MRF intake and sorting →
an append-only batch ledger (suspected vs evidence-verified MLP) → processing partners → evidence-reviewed recycling
outcomes, with ESP32 smart-bin telemetry, photo-based packaging suggestions, finance, reports and EN / HI / TE UI.

> **Honesty notice.** Everything shipped as demo data is synthetic and labelled as such in the UI, exports and API
> (`data_origin`). The vision module ships **without a trained model**; its demo heuristic is not a classifier and no accuracy
> is claimed. Route distances are straight-line estimates unless an OSRM server is configured. Dispatching material is never
> counted as recycling. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for exactly what is done.

## Quick start (Docker)

Requirements: Docker with Compose v2. Nothing else needs to be installed on the host.

```bash
cp .env.example .env          # development defaults; change every secret before sharing the stack
docker compose up --build -d  # db (PostGIS), mosquitto, api, worker, web
docker compose exec api python -m app.scripts.seed_demo --reset   # synthetic demo data
```

| What | URL |
|---|---|
| Web app (PWA) | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/api/v1/health |
| MQTT broker | localhost:1883 (auth + per-device ACL) |

Port clashes? Set `WEB_HOST_PORT`, `API_HOST_PORT`, `MQTT_HOST_PORT`, `DB_HOST_PORT` in `.env`.

### Demo accounts (development only)

Every demo account uses the password **`PlasticLoop@2026`** (printed by the seed script and shown on the login page in demo
mode only; refused when `ENVIRONMENT=production`).

| Role | Email |
|---|---|
| Super admin | `superadmin@plasticloop.example` |
| Panchayat admin | `gp.vanapuram@plasticloop.example`, `gp.pachchapalli@…`, `gp.neelagiri@…` |
| Collector | `collector1@plasticloop.example` … `collector6@…` |
| Driver | `driver.vanapuram@plasticloop.example`, `driver.pachchapalli@…` |
| MRF / PWMU operator | `mrf.operator@plasticloop.example` |
| Processing partner (fictional) | `processor@plasticloop.example` |
| Household | `household@plasticloop.example` |
| Evaluator (read-only + guided demo) | `evaluator@plasticloop.example` |

Start with **Guided demo** (`/demo`, as the evaluator): 12 steps that run the real services end to end. Script:
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Common commands

```bash
docker compose exec api python -m pytest -q                       # backend tests (98)
docker compose exec api python -m app.scripts.seed_demo --reset   # reset demo data
docker compose exec api python /simulators/iot-device/simulator.py --device-id DEV-ESP32-001 --demo-key --mqtt-host mosquitto
sh infra/scripts/e2e.sh                                           # Playwright E2E against the running stack
sh infra/scripts/backup.sh                                        # DB + uploads backup  (restore.sh to restore)
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/esp32/plasticloop_node
```

Development with hot reload (API bind-mounted, Next.js dev server in a container):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db mosquitto api worker web-dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec web-dev sh -c "cd /repo/apps/web && npx vitest run && npx tsc --noEmit && npx eslint src tests"
```

After API schema changes: `python -m app.scripts.export_openapi openapi.json` (in `api`) then `pnpm gen:api` (in `web-dev`)
regenerates the TypeScript types in `packages/shared-schemas`.

## Repository layout

```
apps/api            FastAPI + SQLAlchemy 2 + Alembic (PostGIS), OR-Tools routing, OpenCV vision adapters, MQTT worker
apps/web            Next.js (App Router) PWA, Tailwind + shadcn/ui, TanStack Query, Dexie offline queue, Leaflet maps
packages/           design tokens, OpenAPI-generated TypeScript types
firmware/esp32      ESP32 node sketch (HX711 load cell, HC-SR04 fill level, MQTT/HTTPS)
simulators          IoT device simulator (labelled synthetic)
infra               Mosquitto config, backup / restore / E2E scripts
docs                architecture, API, ESP32, traceability, tests, demo, deployment, implementation status
```

## Documentation

* [Architecture](docs/ARCHITECTURE.md) · [API reference](docs/API_REFERENCE.md) · [ESP32 integration](docs/ESP32_INTEGRATION.md)
* [Requirements traceability](docs/REQUIREMENTS_TRACEABILITY.md) · [Test report](docs/TEST_REPORT.md) · [Demo script](docs/DEMO_SCRIPT.md)
* [Deployment (VPS, TLS, backups)](docs/DEPLOYMENT.md) · [Implementation status](docs/IMPLEMENTATION_STATUS.md)

## Licence and data

Demo villages, people, organisations and partners are fictional. No real government records, recycling partners or
regulatory approvals are represented. Hindi and Telugu strings are machine-drafted and need native-speaker review.
