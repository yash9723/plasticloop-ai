# Architecture

## System overview

```
 Households / collectors / drivers / panchayat / MRF / processors / evaluators (browser or installed PWA)
                │  HTTPS (same origin)
         ┌──────▼──────┐   /api/v1/* proxied   ┌──────────────┐   SQL    ┌────────────────────┐
         │  web        │ ────────────────────▶ │  api         │ ───────▶ │ db: PostgreSQL 16  │
         │  Next.js    │                       │  FastAPI     │ ◀─────── │ + PostGIS          │
         │  PWA + SW   │ ◀── SSE (live events) │              │  NOTIFY  └────────────────────┘
         └─────────────┘                       └──────┬───────┘                ▲
                                                      │ writes broker          │ SQL
  ESP32 nodes ── MQTT (auth + ACL) ──▶ ┌───────────┐  │ credentials            │
  simulator   ── HTTPS (Device key) ─▶ │ mosquitto │◀─┘                 ┌──────┴──────┐
                                       │           │ ──── subscribe ──▶ │ worker      │
                                       └───────────┘ ◀─── commands ──── │ MQTT ingest │
                                                                        │ + periodic  │
                                                                        └─────────────┘
```

Five containers (`docker-compose.yml`): **db** (postgis/postgis:16-3.4), **mosquitto** (2.0), **api** (FastAPI/uvicorn),
**worker** (same image as api: MQTT subscriber + 60 s checks) and **web** (Next.js standalone server). No other services:
no Redis, no message queue, no paid APIs.

## Key decisions

| Decision | Why | Trade-off / upgrade path |
|---|---|---|
| One API + one worker process | Smallest thing that covers HTTP + MQTT + periodic jobs | Scale the API horizontally; move the in-process rate limiter to Redis then |
| No repository layer | SQLAlchemy session is already the unit of work; business rules live in `app/services` | — |
| PostgreSQL constraints do the hard guarantees | Append-only triggers on `audit_logs` and `batch_movements`; CHECKs on weights, balances, enums; `version` columns for optimistic locking | Every rule is enforced even if a future endpoint forgets it |
| Weights `NUMERIC(12,3)` kg, money `BIGINT` paise | No float rounding in ledgers or finance | UI formats for display; exact values used where users must match a recorded figure |
| Same-origin API via Next.js rewrite | No CORS in browsers; refresh cookie is `SameSite=Strict`, path-scoped | `API_INTERNAL_URL` is baked in at build time |
| Server-sent events from Postgres `NOTIFY` | Live dashboards without a broker for the browser | One DB connection per open stream (see `ponytail:` note in `events.py`) |
| Custom i18n (`useT`, JSON catalogues, CI check) | 3 languages, ~1 200 keys, no runtime dependency | `scripts/check-i18n.mjs` fails on missing keys / placeholder mismatch |
| Hand-written service worker | Full control over what is cached for offline collection | Background Sync is not assumed; sync runs while the app is open |

## Backend (`apps/api`)

* `app/core` — settings (production guards refuse demo mode and dev secrets), JSON logging with request IDs, error schema
  `{"error":{code,message,details,request_id}}`, security headers, rate limiting.
* `app/security` — Argon2id passwords; 15-min HS256 access JWT held in memory by the client; opaque refresh tokens stored as
  SHA-256, rotated per use, **reuse revokes the whole family**; CSRF header on cookie-authenticated endpoints;
  `AccessScope` (village / facility / organisation / partner / household) applied to every query. Other tenants' records
  return 404, not 403.
* `app/models` — 48 tables (identity, collection, IoT, logistics, MRF, recovery, finance, media, vision, audit). Locations are
  PostGIS `geography` columns generated from lat/lng with GIST indexes.
* `app/services` — collections + idempotent offline sync (per-event SAVEPOINT; accepted / duplicate / conflict / rejected),
  telemetry (quality flags, alerts, NOTIFY), inventory (row locks + version checks, sort/split/merge/adjust, MLP evidence
  review, mass balance), route planner, recovery (transfers, evidence-gated outcomes), notifications, audit, media
  (magic-byte check, EXIF-stripping re-encode, HMAC-signed short-lived URLs), guided demo.
* `app/routing` — distance matrix (OSRM `/table` if `OSRM_URL`, else haversine × 1.3 **labelled estimate**) and OR-Tools CVRP
  with time windows, max shift, priority-weighted drop penalties, mandatory emergency stops, plus a fixed-order baseline on the
  same matrix and stop set (savings are only reported for comparable plans).
* `app/ai` — adapters: `trained` (Ultralytics YOLO-cls, only if weights *and* package exist), `demo_heuristic` (OpenCV colour /
  texture rules, labelled not-a-model), `manual_only`. Dataset split, evaluation (confusion matrix, per-class P/R/F1) and
  optional training scripts. Suggestions and human reviews are stored separately.
* `app/worker.py` — MQTT subscriber (`plasticloop/devices/+/telemetry|status`), device offline detection, overdue pickups,
  ageing stock alerts, broker credential file refresh.

### Data provenance

`data_origin ∈ {live, demo_seed, simulated}` on events, readings, intakes, batches, transfers, outcomes, sales, expenses.
`measurement_source ∈ {device_measured, manual_entry, simulated_sensor, estimated}` on collections; a weight is only
`device_measured` when it references a real device reading that matches. Recovered quantities are split into
*evidence reviewed* / *evidence submitted* / *self-reported*; only the first is counted as recovered anywhere.

### Material flow and ledger

```
collection_events ──(declared)──▶ facility_intakes (gross − tare = net)
                                        │ INTAKE
                                        ▼
                             material_batches (mixed/unsorted) ──SORT_OUT──▶ children (SORT_IN): rigid, film,
                             suspected_mlp (always SUSPECTED), paper, metal, rejects; difference kept on the operation
                                        │ SPLIT / MERGE / LOSS / DISPOSAL / ADJUSTMENT (reason required)
                                        ▼
                     processing_transfers: allocated → dispatched (TRANSFER_OUT) → received (discrepancy) →
                     accepted / partially accepted / rejected (optional TRANSFER_RETURN) → outcomes (evidence) → review
```

Every weight change is one signed row in `batch_movements` (append-only, enforced by trigger); a batch's weight always
equals the sum of its movements, and mass balance reports unexplained differences against a configurable tolerance.

## Frontend (`apps/web`)

* App Router with `(public)` and `(app)` route groups; role-aware navigation; every page uses TanStack Query against the typed
  API (`packages/shared-schemas`, generated from OpenAPI).
* Offline collector: Dexie (IndexedDB) queue with statuses `draft → queued → syncing → synced | conflict | failed`;
  immutable `event_id` per record (server de-duplicates); exponential backoff with jitter; photos uploaded before their event.
* Service worker (`src/sw/sw.template.js`, version-stamped at build): cache-first for hashed static assets, network-first for
  pages and RSC with offline fallback, and the JS/CSS referenced by cached pages is cached too, so the collector app and its
  offline queue run with no network.
* Leaflet maps (OpenStreetMap tiles; markers and routes still draw without tiles), Recharts charts, light/dark themes,
  EN / HI / TE.

## IoT

Per-device random key (shown once). HTTPS ingestion verifies a SHA-256 of the key; Mosquitto uses a `password_file` written
by the API with `$7$` PBKDF2-SHA512 hashes and an ACL that lets device `%u` publish only to its own telemetry/status topics
and read only its own command topic. The worker connects as a service user. See [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md).

## Security notes

* Secrets only via environment; production refuses default secrets and demo mode.
* Uploads: 5 MB limit, content sniffing, images re-encoded (EXIF/GPS stripped), served via expiring HMAC URLs.
* Household PII is minimised and masked for roles that do not need it; household-type collection points show approximate
  coordinates to non-field roles; households can be erased.
* CSP and security headers on the web app; `no-store` on API responses; audit log for every write.
