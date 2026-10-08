# API reference

Generated from the running application's OpenAPI document (`python -m app.scripts.api_reference`). The interactive version
with request/response schemas is served at **`/docs`** (Swagger UI) and the raw schema at **`/api/v1/openapi.json`**.

* Base path: `/api/v1`. Browsers reach it through the web app (`/api/v1/*` is proxied), so everything is same-origin.
* Auth: `POST /api/v1/auth/login` returns a 15-minute access token (send `Authorization: Bearer <token>`) and sets an httpOnly
  refresh cookie; `POST /api/v1/auth/refresh` (with header `X-Requested-With: plasticloop`) rotates it.
* Devices: `Authorization: Device <device_id>:<device_key>` on `POST /api/v1/devices/telemetry` only.
* Errors: always `{"error": {"code", "message", "details", "request_id"}}`; cross-tenant ids return 404, missing roles 403.
* Lists: `page`, `page_size` (≤ 200), `sort` (field, `-` prefix for descending) → `{"items", "total", "page", "page_size"}`.
* Weights are kilograms (3 decimals), money is integer paise, timestamps are ISO-8601 with offset.

161 operations in 29 groups.


## analytics

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/analytics/operations` | Funnel, per-village / per-collector totals, device data quality, routes and inventory ageing |
| `GET` | `/api/v1/analytics/overview` | KPI cards + collection time series |
| `GET` | `/api/v1/analytics/public-impact` | Public, aggregate-only impact figures (no personal data) |

## audit

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/audit-logs` | Append-only audit trail (read-only) |

## auth

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/auth/change-password` | Change Password |
| `GET` | `/api/v1/auth/invitations` | List Invitations |
| `POST` | `/api/v1/auth/invitations` | Invite a staff user (scope-limited) |
| `POST` | `/api/v1/auth/invitations/accept` | Accept Invitation |
| `GET` | `/api/v1/auth/invitations/lookup/{token}` | Public: show what an invite is for |
| `DELETE` | `/api/v1/auth/invitations/{invitation_id}` | Revoke Invitation |
| `POST` | `/api/v1/auth/login` | Sign in with email/phone + password |
| `POST` | `/api/v1/auth/logout` | Revoke this session |
| `GET` | `/api/v1/auth/me` | Me |
| `POST` | `/api/v1/auth/refresh` | Rotate the refresh cookie and get a new access token |
| `POST` | `/api/v1/auth/register` | Citizen self-registration (household role only) |

## collection-points

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/collection-points` | List Points |
| `POST` | `/api/v1/collection-points` | Create Point |
| `GET` | `/api/v1/collection-points/by-qr/{qr_code}` | By Qr |
| `GET` | `/api/v1/collection-points/nearby` | PostGIS radius search |
| `GET` | `/api/v1/collection-points/{point_id}` | Get Point |
| `PATCH` | `/api/v1/collection-points/{point_id}` | Update Point |
| `POST` | `/api/v1/collection-points/{point_id}/regenerate-qr` | Rotate a lost or damaged QR label |

## collections

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/collections` | List Collections |
| `POST` | `/api/v1/collections` | Record a collection while online (idempotent) |
| `GET` | `/api/v1/collections/assignments` | List Assignments |
| `POST` | `/api/v1/collections/assignments` | Create Assignments |
| `GET` | `/api/v1/collections/my-tasks` | Collector's stops + offline cache bundle |
| `GET` | `/api/v1/collections/{event_id}` | Get Collection |
| `GET` | `/api/v1/collections/{event_id}/receipt` | Receipt |
| `PATCH` | `/api/v1/collections/{event_id}/review` | Review Collection |

## complaints

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/complaints` | List Complaints |
| `POST` | `/api/v1/complaints` | Create Complaint |
| `GET` | `/api/v1/complaints/{complaint_id}` | Get Complaint |
| `PATCH` | `/api/v1/complaints/{complaint_id}` | Update Complaint |

## demo

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/demo/accounts` | Demo sign-in accounts (development/test only) |
| `POST` | `/api/v1/demo/devices/{device_pk}/simulate` | Inject SIMULATED telemetry through the real ingestion service |
| `GET` | `/api/v1/demo/status` | Is this a demo deployment? |
| `GET` | `/api/v1/demo/walkthrough` | Guided demo: the 12 steps and what each one produced |
| `POST` | `/api/v1/demo/walkthrough/reset` | Forget walkthrough progress (created records stay, labelled synthetic) |
| `POST` | `/api/v1/demo/walkthrough/{n}` | Run one guided-demo step |

## devices

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/devices` | List Devices |
| `POST` | `/api/v1/devices` | Register a device and provision its key (shown once) |
| `GET` | `/api/v1/devices/latest-reading` | Latest OK reading for the collector 'read scale' button |
| `POST` | `/api/v1/devices/telemetry` | HTTPS telemetry from a device |
| `GET` | `/api/v1/devices/{device_pk}` | Get Device |
| `PATCH` | `/api/v1/devices/{device_pk}` | Update Device |
| `GET` | `/api/v1/devices/{device_pk}/calibrations` | Calibrations |
| `POST` | `/api/v1/devices/{device_pk}/calibrations` | Record a manual calibration |
| `POST` | `/api/v1/devices/{device_pk}/commands` | Send a command over MQTT (tare, calibrate, set_interval, reboot, ping) |
| `GET` | `/api/v1/devices/{device_pk}/readings` | Readings |
| `POST` | `/api/v1/devices/{device_pk}/revoke` | Revoke all credentials (device can no longer connect) |
| `POST` | `/api/v1/devices/{device_pk}/rotate-key` | Issue a new key; the old one stops working |

## events

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/events/stream` | Live operational events (text/event-stream) |

## facilities

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/facilities` | List Facilities |
| `POST` | `/api/v1/facilities` | Create Facility |
| `GET` | `/api/v1/facilities/{facility_id}` | Get Facility |
| `GET` | `/api/v1/facilities/{facility_id}/intakes` | List Intakes |
| `POST` | `/api/v1/facilities/{facility_id}/intakes` | Weigh in a delivery: creates a mixed/unsorted batch and an INTAKE ledger movement |
| `GET` | `/api/v1/facilities/{facility_id}/mass-balance` | Get Mass Balance |
| `GET` | `/api/v1/facilities/{facility_id}/stock` | Current stock by material category |
| `GET` | `/api/v1/facilities/{facility_id}/villages` | Villages that deliver to this facility |

## finance

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/finance/expenses` | List Expenses |
| `POST` | `/api/v1/finance/expenses` | Add Expense |
| `GET` | `/api/v1/finance/sales` | List Sales |
| `POST` | `/api/v1/finance/sales/{sale_id}/payments` | Record a payment received (no money moves here) |
| `GET` | `/api/v1/finance/summary` | Revenue, receipts, receivables and expenses for a period |

## health

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/health` | Component status (honest capability report) |
| `GET` | `/api/v1/health/live` | Process is up |
| `GET` | `/api/v1/health/ready` | Database (with PostGIS) reachable |

## households

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/households` | List Households |
| `POST` | `/api/v1/households` | Create Household |
| `DELETE` | `/api/v1/households/{household_id}` | Erase personal data (retention policy); keeps anonymous traceability |
| `GET` | `/api/v1/households/{household_id}` | Get Household |
| `PATCH` | `/api/v1/households/{household_id}` | Update Household |

## inventory

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/inventory/batches` | List Batches |
| `GET` | `/api/v1/inventory/batches/{batch_id}` | Batch Detail |
| `POST` | `/api/v1/inventory/batches/{batch_id}/adjust` | Record a loss, disposal or correction (reason required) |
| `POST` | `/api/v1/inventory/batches/{batch_id}/mlp-review` | Evidence review of a suspected multilayer-plastic batch (never automatic) |
| `POST` | `/api/v1/inventory/batches/{batch_id}/sort` | Sort a batch into measured fractions |
| `POST` | `/api/v1/inventory/batches/{batch_id}/split` | Split |
| `POST` | `/api/v1/inventory/merge` | Merge |

## marketplace

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/marketplace/listings` | List Listings |
| `POST` | `/api/v1/marketplace/listings` | Create Listing |
| `POST` | `/api/v1/marketplace/listings/{listing_id}/offers` | Ask for a quote or make an offer |
| `POST` | `/api/v1/marketplace/listings/{listing_id}/withdraw` | Withdraw |
| `POST` | `/api/v1/marketplace/offers/{offer_id}/respond` | Respond |
| `POST` | `/api/v1/marketplace/offers/{offer_id}/sale` | Record the sale for an accepted offer (moves stock out) |

## media

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/media` | Upload a photo or document (≤ MAX_UPLOAD_MB) |
| `GET` | `/api/v1/media/{media_id}` | Metadata + a fresh short-lived URL |
| `GET` | `/api/v1/media/{media_id}/content` | File bytes (requires a valid signed URL) |

## notifications

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/notifications` | List Notifications |
| `GET` | `/api/v1/notifications/preferences` | Get Preferences |
| `PUT` | `/api/v1/notifications/preferences` | Set Preferences |
| `POST` | `/api/v1/notifications/read-all` | Mark All Read |
| `GET` | `/api/v1/notifications/types` | Types |
| `GET` | `/api/v1/notifications/unread-count` | Unread Count |
| `POST` | `/api/v1/notifications/{notification_id}/read` | Mark Read |

## organizations

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/organizations` | List Organizations |
| `POST` | `/api/v1/organizations` | Create Organization |
| `GET` | `/api/v1/organizations/{org_id}` | Get Organization |
| `PATCH` | `/api/v1/organizations/{org_id}` | Update Organization |

## pickup-requests

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/pickup-requests` | List Requests |
| `POST` | `/api/v1/pickup-requests` | Create Request |
| `PATCH` | `/api/v1/pickup-requests/{request_id}` | Update Request |

## processing-transfers

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/processing-transfers` | List Transfers |
| `POST` | `/api/v1/processing-transfers` | Allocate part of a batch to a processing partner |
| `GET` | `/api/v1/processing-transfers/outcomes/all` | Outcomes across visible transfers (recovery page) |
| `POST` | `/api/v1/processing-transfers/outcomes/{outcome_id}/review` | Review submitted evidence (not by the processor) |
| `GET` | `/api/v1/processing-transfers/{transfer_id}` | Get Transfer |
| `POST` | `/api/v1/processing-transfers/{transfer_id}/cancel` | Cancel |
| `POST` | `/api/v1/processing-transfers/{transfer_id}/decide` | Processor accepts / rejects received material |
| `POST` | `/api/v1/processing-transfers/{transfer_id}/dispatch` | Dispatch |
| `POST` | `/api/v1/processing-transfers/{transfer_id}/outcomes` | Processor reports what happened to accepted material (evidence needed for recycling claims) |
| `POST` | `/api/v1/processing-transfers/{transfer_id}/receive` | Processor confirms the weight received |

## processors

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/processors` | List Partners |
| `POST` | `/api/v1/processors` | Register a processing partner (creates its organisation) |
| `GET` | `/api/v1/processors/{partner_id}` | Get Partner |
| `POST` | `/api/v1/processors/{partner_id}/documents` | Partner submits authorisation documents for review |
| `POST` | `/api/v1/processors/{partner_id}/documents/review` | Record that partner documents were checked |

## reports

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/reports/summary.pdf` | One-page PDF summary for the period |
| `GET` | `/api/v1/reports/{kind}.csv` | Download a CSV export for the period |

## routes

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/routes` | List Routes |
| `GET` | `/api/v1/routes/candidates` | Points due for collection (full, requested or scheduled) |
| `POST` | `/api/v1/routes/plan` | Optimise routes with OR-Tools; preview by default, `save: true` creates routes |
| `GET` | `/api/v1/routes/{route_id}` | Get Route |
| `POST` | `/api/v1/routes/{route_id}/cancel` | Cancel Route |
| `POST` | `/api/v1/routes/{route_id}/complete` | Complete Route |
| `POST` | `/api/v1/routes/{route_id}/delay` | Report Delay |
| `POST` | `/api/v1/routes/{route_id}/start` | Start Route |
| `POST` | `/api/v1/routes/{route_id}/stops/{stop_id}` | Mark a stop collected or skipped (reason required) |

## settings

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/settings/material-categories` | List Categories |
| `GET` | `/api/v1/settings/system` | Get System |
| `PATCH` | `/api/v1/settings/system` | Update System |
| `GET` | `/api/v1/settings/waste-streams` | List Streams |
| `POST` | `/api/v1/settings/waste-streams` | Create Stream |
| `PATCH` | `/api/v1/settings/waste-streams/{stream_id}` | Update Stream |

## sync

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/v1/sync/batch` | Idempotent offline sync with per-event acknowledgement |
| `GET` | `/api/v1/sync/conflicts` | Unresolved payload conflicts in my villages |
| `POST` | `/api/v1/sync/conflicts/{event_id}/resolve` | Keep the original or apply the newer offline version (audited) |
| `GET` | `/api/v1/sync/receipts` | My recent server acknowledgements |

## users

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/users` | List Users |
| `GET` | `/api/v1/users/assignable` | Collectors/drivers that can be assigned in a village |
| `PATCH` | `/api/v1/users/me` | Update Me |
| `GET` | `/api/v1/users/roles` | List Roles |
| `GET` | `/api/v1/users/{user_id}` | Get User |
| `POST` | `/api/v1/users/{user_id}/activate` | Activate |
| `POST` | `/api/v1/users/{user_id}/deactivate` | Deactivate |

## vehicles

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/vehicles` | List Vehicles |
| `POST` | `/api/v1/vehicles` | Create Vehicle |
| `PATCH` | `/api/v1/vehicles/{vehicle_id}` | Update Vehicle |

## villages

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/villages` | List Villages |
| `POST` | `/api/v1/villages` | Create Village |
| `GET` | `/api/v1/villages/public` | Public list for citizen registration (names only) |
| `GET` | `/api/v1/villages/{village_id}` | Get Village |
| `PATCH` | `/api/v1/villages/{village_id}` | Update Village |

## vision

| Method | Path | Summary |
|---|---|---|
| `GET` | `/api/v1/vision/agreement` | How often reviewers agreed with suggestions (reviewed samples only; not an accuracy figure) |
| `POST` | `/api/v1/vision/classify` | Get a SUGGESTED label for a packaging photo |
| `GET` | `/api/v1/vision/labels` | Labels |
| `GET` | `/api/v1/vision/predictions` | Review queue (low-confidence first) |
| `POST` | `/api/v1/vision/predictions/{prediction_id}/review` | Record the human-verified label |
| `GET` | `/api/v1/vision/status` | Which classifier is active, and any measured evaluation |
