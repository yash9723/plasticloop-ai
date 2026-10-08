# Demo script (about 10 minutes)

Before the demo: `docker compose exec api python -m app.scripts.seed_demo --reset`. All data is synthetic; say so once at the
start and point at the yellow banner — it stays on every page in demo mode.

## 1. The problem in one screen (1 min)
Sign in as **`evaluator@plasticloop.example`** (password `PlasticLoop@2026`). **Dashboard**: kilograms collected, pending
pickups, devices online, suspected vs verified MLP, and recovered material split into *evidence reviewed* vs *self-reported*.
Point out that "recovered" never includes material that was merely sent to a processor.

## 2. Guided demo (5 min)
Open **Guided demo** and run the 12 steps; each runs the real services as the named demo account:

| # | Step | What to point at |
|---|---|---|
| 1 | Household requests a pickup | Notification to the panchayat |
| 2 | Smart bin reports 92 % | SIMULATED device, fill alert, quality check passed |
| 3 | Panchayat plans tomorrow's route | OR-Tools; the request is an emergency stop; distance labelled *estimate*; fixed-order baseline on the same stops |
| 4 | Collector records offline, syncs | Phone retries: first `accepted`, second `duplicate` — no double counting |
| 5 | MRF weighs in | Gross − tare = net; declared vs weighed gap kept |
| 6 | Sorting | MLP recorded as **suspected**; 0.5 kg difference kept, not erased |
| 7 | Photo suggestion + review | Demo heuristic (not a model) suggests a label; the operator confirms or corrects it |
| 8 | MLP verified with evidence | Only an uploaded (synthetic) test record + reviewer makes it *verified* |
| 9 | Dispatch to processor | `counted_as_recycled: false` |
| 10 | Receive and accept | Weight difference recorded |
| 11 | Outcome + evidence review | `submitted` → reviewed by a different person → counts as recovered |
| 12 | Impact | Funnel for the last 24 h |

Click the links under each step to show the real records (route map, batch ledger, transfer timeline).

## 3. Field reality (2 min)
Sign in as **`collector1@…`** on a phone-sized window. Collector app → turn the network off (browser dev tools) → record a
collection → reload → it is still there → network on → **Sync now**. Open **Offline queue** to show statuses.

## 4. Devices (1 min)
As **`gp.vanapuram@…`**: **Devices → Device simulator** → raise fill to 95 % → **Send reading** → the device page and the bin's
fill update live. Mention the real ESP32 firmware and the per-device MQTT ACL.

## 5. Accountability (1 min)
**Inventory → any batch**: append-only ledger and lineage. **Facilities → mass balance** with the tolerance flag.
**Reports** → download the PDF summary (it states that synthetic data is included). **Audit logs** (evaluator).

## Questions you will get
* *Is the vision model accurate?* — There is no trained model in the repo; the heuristic is labelled as such and no accuracy is
  claimed. The evaluation script reports real metrics once a labelled dataset exists.
* *Are the route savings real?* — They are computed on straight-line estimates unless OSRM is configured, and only against a
  fixed-order baseline on the same stops.
* *Is recycling verified?* — Only outcomes with evidence reviewed by someone other than the processor count.
