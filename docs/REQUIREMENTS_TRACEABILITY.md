# Requirements traceability

Status: ✅ implemented and verified (test or recorded manual run) · 🟡 implemented with a stated limit · ⬜ not implemented.
Evidence names refer to [TEST_REPORT.md](TEST_REPORT.md).

| Requirement area | Implementation | Evidence | Status |
|---|---|---|---|
| 8 roles (super admin, panchayat admin, collector, driver, MRF operator, processor, household, evaluator) | `RoleKey`, `user_memberships`, `require()`, `AccessScope`; role-aware navigation | `test_permissions.py`, E2E roles test | ✅ |
| Tenant isolation | Every query filtered by scope; foreign records → 404 | permissions, devices, inventory, routing, recovery tests | ✅ |
| Auth security | Argon2id, short JWT, rotating refresh cookie with reuse detection, CSRF header, rate limits, production guards | `test_auth.py` | ✅ |
| Households & collection points | Households (PII minimised, erasure), QR points with PostGIS nearby search, schedules, streams | `test_collections_sync.py`, browser | ✅ |
| Smart collection (pickup requests, assignments, receipts, complaints) | `/pickup-requests`, `/collections`, receipts, complaints | backend tests, guided demo steps 1 & 4 | ✅ |
| Offline-first collector PWA | Dexie queue, immutable event ids, backoff, service worker caching | vitest sync tests, E2E offline test | ✅ (foreground sync; Background Sync not assumed) |
| Idempotent sync & conflicts | Per-event savepoints, payload hashing, admin conflict resolution | `test_collections_sync.py`, E2E (exactly one row) | ✅ |
| Device integration (ESP32, MQTT, HTTPS) | Registration/keys, ingestion, quality flags, alerts, commands, calibration, ACL, worker | `test_devices.py`, manual broker checks, firmware compile | 🟡 firmware not run on hardware |
| Simulator (labelled) | CLI + web simulator; readings always synthetic | `test_devices.py`, manual | ✅ |
| AI classification (honest) | Trained / heuristic / manual adapters, review queue, evaluation & training scripts | `test_vision.py` | 🟡 no dataset or trained model shipped → no accuracy claimed |
| Never auto-verify MLP | Sorting yields *suspected*; verification only via evidence review | `test_inventory.py`, demo steps 6–8 | ✅ |
| Route optimisation | OR-Tools CVRP + time windows + priorities + emergency; fixed-order baseline; labelled distance basis | `test_routing.py`, browser | 🟡 road distances need OSRM (not tested) |
| MRF intake, inventory, ledger, mass balance | Intake, sort/split/merge/adjust, append-only ledger, mass balance with tolerance | `test_inventory.py`, browser | ✅ |
| Processor transfers & outcomes | Allocation → dispatch → receipt → decision → outcome → independent evidence review | `test_recovery.py`, demo steps 9–11, browser | ✅ |
| Collected ≠ recycled | Funnel separates dispatched/accepted/reviewed recovery; self-reported never counted | `test_recovery.py` | ✅ |
| Marketplace | Listings, quotes/offers, acceptance, sale with ledger movement; hypothetical prices labelled | `test_recovery.py` | ✅ |
| Finance | Sales, payments, expenses with estimates separated, cost per kg | `test_recovery.py` | ✅ |
| Reports | CSV exports (6 kinds), PDF summary noting synthetic data | `test_recovery.py` | ✅ |
| Analytics | Overview KPIs, funnel, by village/collector, device quality, routes vs baseline, stock ageing | browser, demo step 12 | ✅ |
| Notifications | In-app, dedupe/cooldown, muting; fill, battery, offline, anomalies, pickups, routes, transfers, ageing | device & recovery tests, worker logs | 🟡 in-app only (no SMS/WhatsApp/push) |
| Live updates | Postgres NOTIFY → SSE → query invalidation | manual (browser) | ✅ |
| Multilingual EN / HI / TE | Custom i18n, CI parity check, language persisted | i18n check, vitest parity test | 🟡 HI/TE need native review |
| Accessibility & responsive | Semantic structure, labels, contrast fixes, no overflow 360–1440 px | E2E axe + overflow tests | 🟡 screen readers not tested |
| Database design | 48 tables, constraints, triggers, PostGIS, migrations | `test_db_constraints.py`, `alembic upgrade` on clean DB | ✅ |
| API design | Versioned REST, uniform errors, pagination, OpenAPI (161 operations) | [API_REFERENCE.md](API_REFERENCE.md) | ✅ |
| Demo data & hackathon mode | Deterministic synthetic seed via real services; demo banner; 12-step guided demo; demo disabled in production | `test_demo_walkthrough.py` | ✅ |
| Audit trail | Append-only `audit_logs`, audit page | constraints test, browser | ✅ |
| DevOps | Docker Compose (5 services), healthchecks, backup/restore, E2E script, deployment guide | clean-stack run, backup round trip | 🟡 public TLS deployment not executed |
| Hardware contract | Topics, payloads, commands, wiring, provisioning, calibration | [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md) | 🟡 bench test pending |
| Documentation | README, architecture, API reference, ESP32, traceability, tests, demo, deployment, status | this folder | ✅ |
