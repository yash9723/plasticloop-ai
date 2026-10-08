"""Deterministic SYNTHETIC demo data.

Every organisation, village, person, device, number and outcome created here is fictional and labelled as such
(`is_sample=True`, `data_origin=demo_seed`, names suffixed "(synthetic)" / "(fictional sample)", e-mails on the
reserved `.example` TLD). Nothing here is real pilot evidence.

    python -m app.scripts.seed_demo --reset
"""

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.models import (
    CollectionAssignment,
    CollectionEvent,
    CollectionPoint,
    Complaint,
    Household,
    Notification,
    Organization,
    PickupRequest,
    User,
    UserMembership,
    Village,
    WasteStream,
)
from app.models.enums import (
    AssignmentStatus,
    ComplaintStatus,
    DataOrigin,
    MeasurementSource,
    OrgType,
    PickupStatus,
    RoleKey,
    Severity,
)
from app.security.passwords import hash_password
from app.services.collections import payload_hash

DEMO_PASSWORD = "PlasticLoop@2026"  # development/demo only; the seed refuses to run in production
DOMAIN = "plasticloop.example"  # RFC 2606 reserved TLD: cannot belong to a real person
KEEP_TABLES = {"roles", "material_categories", "alembic_version", "spatial_ref_sys"}

DEMO_ACCOUNTS: list[tuple[str, str, str]] = [
    (f"superadmin@{DOMAIN}", "super_admin", "Super Admin"),
    (f"gp.vanapuram@{DOMAIN}", "gp_admin", "Panchayat admin, Vanapuram"),
    (f"gp.pachchapalli@{DOMAIN}", "gp_admin", "Panchayat admin, Pachchapalli"),
    (f"gp.neelagiri@{DOMAIN}", "gp_admin", "Panchayat admin, Neelagiri Thanda"),
    (f"collector1@{DOMAIN}", "collector", "Collector, Vanapuram"),
    (f"collector2@{DOMAIN}", "collector", "Collector, Vanapuram"),
    (f"collector3@{DOMAIN}", "collector", "Collector, Pachchapalli"),
    (f"collector4@{DOMAIN}", "collector", "Collector, Pachchapalli"),
    (f"collector5@{DOMAIN}", "collector", "Collector, Neelagiri Thanda"),
    (f"collector6@{DOMAIN}", "collector", "Collector, Neelagiri Thanda"),
    (f"driver.vanapuram@{DOMAIN}", "driver", "Driver, Vanapuram"),
    (f"driver.pachchapalli@{DOMAIN}", "driver", "Driver, Pachchapalli"),
    (f"mrf.operator@{DOMAIN}", "mrf_operator", "MRF / PWMU operator"),
    (f"processor@{DOMAIN}", "processor", "Processing partner (fictional)"),
    (f"household@{DOMAIN}", "household", "Household / citizen"),
    (f"evaluator@{DOMAIN}", "evaluator", "Read-only evaluator"),
]

# code, name, panchayat, lat, lng, collector numbers, households, points
VILLAGES = [
    ("VNP", "Vanapuram (synthetic)", "Vanapuram Gram Panchayat (synthetic)", 17.9620, 78.8410, (1, 2), 20, 16),
    ("PCP", "Pachchapalli (synthetic)", "Pachchapalli Gram Panchayat (synthetic)", 17.9135, 78.9020, (3, 4), 18, 14),
    ("NGT", "Neelagiri Thanda (synthetic)", "Neelagiri Thanda Gram Panchayat (synthetic)", 17.9980, 78.9105, (5, 6), 12, 10),
]
GP_ADMIN_KEY = {"VNP": "gp.vanapuram", "PCP": "gp.pachchapalli", "NGT": "gp.neelagiri"}
COLLECTOR_NAMES = ["Ramesh Kumar", "Sujatha Bandari", "Venkatesh Rao", "Lakshmi Prasanna", "Mahesh Goud", "Anjali Naik"]
FIRST = ["Srinivas", "Padma", "Raju", "Kavitha", "Narsimha", "Swapna", "Yadagiri", "Manjula", "Ravi", "Saritha",
         "Bhaskar", "Renuka", "Kishan", "Vijaya", "Anil", "Sunitha", "Mallesh", "Jyothi", "Prakash", "Rekha"]
LAST = ["Reddy", "Goud", "Rao", "Yadav", "Naik", "Chary", "Mudiraj", "Kumar", "Banoth", "Gaddam"]
INSTITUTIONS = ["Govt. High School", "Weekly Market", "Anganwadi Centre", "Panchayat Office", "Primary Health Sub-centre"]

# code, label, hi, te, colour, description, rules, typical weight range per pickup (kg)
STREAMS = [
    ("clean_rigid_plastic", "Clean rigid plastic", "साफ़ कठोर प्लास्टिक", "శుభ్రమైన గట్టి ప్లాస్టిక్", "#166534",
     "Bottles, containers, buckets and other hard plastic items, rinsed and dry.",
     ["Rinse and dry", "Remove food residue", "Caps can stay on"], (0.6, 4.0)),
    ("soft_plastic_packets", "Soft plastic & packets", "नरम प्लास्टिक और पैकेट", "మెత్తని ప్లాస్టిక్ & ప్యాకెట్లు", "#0d9488",
     "Carry bags, wrappers, chips/biscuit/milk packets. Shiny foil-lined packets are likely multi-layer (MLP).",
     ["Shake out food", "Keep dry", "Do not burn"], (0.3, 3.0)),
    ("paper_metal_glass", "Paper, metal & glass", "कागज़, धातु और काँच", "కాగితం, లోహం & గాజు", "#64748b",
     "Cardboard, newspaper, tins and glass bottles.", ["Flatten cartons", "Keep glass separate and intact"], (0.5, 5.0)),
    ("mixed_rejects", "Mixed / soiled rejects", "मिश्रित / गंदा कचरा", "కలగలిసిన / మురికి వ్యర్థాలు", "#b45309",
     "Soiled or mixed material that cannot be separated at source.", ["Keep away from wet waste"], (0.2, 2.0)),
]


def ensure_safe() -> None:
    if not settings.demo_enabled:
        raise SystemExit("Refusing to seed: DEMO_MODE is off or ENVIRONMENT=production.")


def reset(db: Session) -> None:
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in KEEP_TABLES]
    db.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    db.commit()


class Seeder:
    def __init__(self, db: Session):
        self.db = db
        self.rng = random.Random(2026)
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.pw = hash_password(DEMO_PASSWORD)
        self.users: dict[str, User] = {}
        self.orgs: dict[str, Organization] = {}
        self.villages: dict[str, Village] = {}
        self.streams: dict[str, WasteStream] = {}
        self.points: dict[str, list[CollectionPoint]] = {}
        self.households: dict[str, list[Household]] = {}
        self.n_events = 0

    # ---------- helpers ----------
    def qr(self) -> str:
        return "PL" + "".join(self.rng.choice("0123456789ABCDEF") for _ in range(10))

    def jitter(self, lat: float, lng: float, spread: float = 0.008) -> tuple[float, float]:
        return round(lat + self.rng.uniform(-spread, spread), 6), round(lng + self.rng.uniform(-spread, spread), 6)

    def org(self, key: str, name: str, org_type: OrgType, code: str) -> Organization:
        o = Organization(name=name, code=code, org_type=org_type, is_sample=True)
        self.db.add(o)
        self.db.flush()
        self.orgs[key] = o
        return o

    def user(self, email: str, name: str, role: str, org: Organization, village: Village | None = None, facility_id=None) -> User:
        u = User(email=email, full_name=name, password_hash=self.pw, is_sample=True, preferred_language="en")
        self.db.add(u)
        self.db.flush()
        self.db.add(UserMembership(user_id=u.id, organization_id=org.id, role_key=role,
                                   village_id=village.id if village else None, facility_id=facility_id))
        self.users[email.split("@")[0]] = u
        return u

    def gp_admin(self, code: str) -> User:
        return self.users[GP_ADMIN_KEY[code]]

    @staticmethod
    def square(lat: float, lng: float, d: float = 0.011) -> dict:
        """Approximate service area for map display only; not a surveyed boundary."""
        ring = [[lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d], [lng - d, lat + d], [lng - d, lat - d]]
        return {"type": "Polygon", "coordinates": [ring], "properties": {"approximate": True, "synthetic": True}}

    # ---------- sections ----------
    def identity(self) -> None:
        platform = self.org("platform", "PlasticLoop Demo Platform (synthetic)", OrgType.PLATFORM, "PL-PLATFORM")
        self.org("operator", "Cluster Waste Services Cooperative (synthetic)", OrgType.MRF_OPERATOR, "PL-MRF-COOP")
        self.org("proc1", "GreenLoop Polymers (fictional sample)", OrgType.PROCESSOR, "PL-PROC-GREENLOOP")
        self.org("proc2", "Deccan Co-processing Partners (fictional sample)", OrgType.PROCESSOR, "PL-PROC-DECCAN")
        self.org("buyer1", "Sample Recycled Materials Buyer A (fictional)", OrgType.BUYER, "PL-BUY-A")
        self.org("buyer2", "Sample Packaging Converter B (fictional)", OrgType.BUYER, "PL-BUY-B")
        self.user(f"superadmin@{DOMAIN}", "Platform Admin (demo)", RoleKey.SUPER_ADMIN, platform)
        self.user(f"evaluator@{DOMAIN}", "SIH Evaluator (demo)", RoleKey.EVALUATOR, platform)

        for code, name, gp_name, lat, lng, collectors, _, _ in VILLAGES:
            gp = self.org(code, gp_name, OrgType.GRAM_PANCHAYAT, f"PL-GP-{code}")
            v = Village(organization_id=gp.id, name=name, code=code, district="Sample District (synthetic)", state="Telangana",
                        lat=lat, lng=lng, population=self.rng.randint(1800, 4200), is_sample=True,
                        boundary_geojson=self.square(lat, lng))
            self.db.add(v)
            self.db.flush()
            self.villages[code] = v
            short = name.split(" (")[0]
            self.user(f"{GP_ADMIN_KEY[code]}@{DOMAIN}", f"Panchayat Secretary, {short} (demo)", RoleKey.GP_ADMIN, gp)
            for idx in collectors:
                self.user(f"collector{idx}@{DOMAIN}", COLLECTOR_NAMES[idx - 1], RoleKey.COLLECTOR, gp, v)
        self.user(f"driver.vanapuram@{DOMAIN}", "Shankar Yadav", RoleKey.DRIVER, self.orgs["VNP"])
        self.user(f"driver.pachchapalli@{DOMAIN}", "Ilaiah Banoth", RoleKey.DRIVER, self.orgs["PCP"])

    def waste_streams(self) -> None:
        for i, (code, label, hi, te, color, desc, rules, _) in enumerate(STREAMS):
            s = WasteStream(code=code, label=label, labels={"hi": hi, "te": te}, description=desc, color=color,
                            rules=rules, sort_order=i, is_demo_config=True)
            self.db.add(s)
            self.streams[code] = s
        self.db.flush()

    def households_and_points(self) -> None:
        streams = list(self.streams.values())
        for code, _, _, lat, lng, collectors, n_households, n_points in VILLAGES:
            v = self.villages[code]
            hh_list = []
            for i in range(n_households):
                hlat, hlng = self.jitter(lat, lng)
                h = Household(village_id=v.id, household_code=f"{code}-HH-{i + 1:03d}",
                              head_name=f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}", phone=None,
                              address_line=f"Ward {self.rng.randint(1, 8)}, House {self.rng.randint(1, 240)} (synthetic)",
                              lat=hlat, lng=hlng, members_count=self.rng.randint(2, 7), consent_at=self.now, is_sample=True)
                self.db.add(h)
                hh_list.append(h)
            self.db.flush()
            self.households[code] = hh_list

            collector_users = [self.users[f"collector{i}"] for i in collectors]
            n_household_points = max(2, n_points // 4)
            points = []
            for i in range(n_points):
                plat, plng = self.jitter(lat, lng)
                if i < n_household_points:
                    hh = hh_list[i]
                    kind, label, hid, plat, plng = "household", f"Household point {hh.household_code}", hh.id, hh.lat, hh.lng
                    chosen, capacity = streams[:2], Decimal("25")
                elif i < n_household_points + 2:
                    kind, label, hid = "institution", f"{INSTITUTIONS[(i + len(code)) % len(INSTITUTIONS)]} (synthetic)", None
                    chosen, capacity = streams, Decimal("60")
                else:
                    kind, label, hid = "community_bin", f"Ward {self.rng.randint(1, 8)} community bin #{i + 1}", None
                    chosen = streams if self.rng.random() < 0.6 else streams[:3]
                    capacity = Decimal("120")
                cp = CollectionPoint(
                    code=f"{code}-CP-{i + 1:03d}", qr_code=self.qr(), name=label, point_type=kind, village_id=v.id,
                    household_id=hid, lat=plat, lng=plng, assigned_collector_id=collector_users[i % len(collector_users)].id,
                    pickup_days=sorted(self.rng.sample(["mon", "tue", "wed", "thu", "fri", "sat"], k=2)),
                    pickup_window="07:00-11:00", bin_capacity_kg=capacity, priority=self.rng.choice([2, 3, 3, 3, 4]),
                    streams=chosen, is_sample=True,
                )
                self.db.add(cp)
                points.append(cp)
            self.db.flush()
            self.points[code] = points

        owner = self.user(f"household@{DOMAIN}", "Padma Reddy (demo citizen)", RoleKey.HOUSEHOLD, self.orgs["VNP"])
        self.households["VNP"][0].user_id = owner.id
        self.households["VNP"][0].head_name = "Padma Reddy (demo citizen)"
        self.db.flush()

    def collection_history(self, days: int = 45) -> None:
        weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        ranges = {s[0]: s[7] for s in STREAMS}
        events = []
        for points in self.points.values():
            for cp in points:
                scale = {"household": 0.5, "institution": 1.6, "community_bin": 2.4}[cp.point_type]
                last = None
                for back in range(days, 0, -1):
                    day = (self.now - timedelta(days=back)).date()
                    if weekdays[day.weekday()] not in cp.pickup_days or self.rng.random() > 0.85:
                        continue
                    when = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=self.rng.uniform(1.5, 5.5))
                    for stream in self.rng.sample(cp.streams, k=min(len(cp.streams), self.rng.choice([1, 2]))):
                        lo, hi = ranges[stream.code]
                        weight = Decimal(str(round(self.rng.uniform(lo, hi) * scale, 2)))
                        eid = uuid.uuid4()
                        payload = {"collection_point_id": str(cp.id), "waste_stream_id": str(stream.id), "weight_kg": str(weight),
                                   "collected_at": when.isoformat(), "measurement_source": "manual_entry"}
                        events.append(CollectionEvent(
                            id=eid, idempotency_key=str(eid), collection_point_id=cp.id, village_id=cp.village_id,
                            collector_id=cp.assigned_collector_id, waste_stream_id=stream.id, weight_kg=weight,
                            measurement_source=MeasurementSource.MANUAL_ENTRY, collected_at=when, client_created_at=when,
                            offline_captured=self.rng.random() < 0.3, data_origin=DataOrigin.DEMO_SEED,
                            payload_hash=payload_hash("collection", payload),
                        ))
                    last = when
                cp.last_collected_at = last
                since = (self.now - last).days if last else 7
                cp.fill_percent = Decimal(str(min(98, round(since * self.rng.uniform(9, 16), 1))))
                cp.fill_source = "estimated"
                cp.fill_updated_at = self.now
        self.db.add_all(events)
        self.db.flush()
        self.n_events = len(events)

    def requests_complaints_assignments(self) -> None:
        today = self.now.date()
        statuses = ([PickupStatus.SUBMITTED] * 4 + [PickupStatus.ASSIGNED] * 3 + [PickupStatus.IN_PROGRESS]
                    + [PickupStatus.COMPLETED] * 3 + [PickupStatus.CANCELLED])
        for i, status in enumerate(statuses):
            code = ("VNP", "PCP", "NGT")[i % 3]
            hh = self.households[code][i % 5]
            cp = next((p for p in self.points[code] if p.household_id == hh.id), self.points[code][0])
            requester = self.users["household"] if hh.user_id else self.gp_admin(code)
            self.db.add(PickupRequest(
                village_id=self.villages[code].id, household_id=hh.id, collection_point_id=cp.id,
                waste_stream_id=self.streams["soft_plastic_packets"].id, requested_by=requester.id, status=status,
                preferred_date=today + timedelta(days=self.rng.randint(0, 3)), estimated_weight_kg=Decimal("3.5"),
                notes="Extra packets after a family function (synthetic)" if i % 4 == 0 else None,
                assigned_collector_id=cp.assigned_collector_id if status != PickupStatus.SUBMITTED else None,
                completed_at=self.now if status == PickupStatus.COMPLETED else None,
                cancelled_reason="Requested by mistake (synthetic)" if status == PickupStatus.CANCELLED else None,
                data_origin=DataOrigin.DEMO_SEED,
            ))
        specs = [
            ("missed_pickup", ComplaintStatus.OPEN, "Scheduled Thursday pickup did not happen (synthetic)."),
            ("overflowing_bin", ComplaintStatus.ASSIGNED, "Community bin near the bus stop is overflowing (synthetic)."),
            ("damaged_bin", ComplaintStatus.UNDER_REVIEW, "Bin lid broken; dogs scatter packets (synthetic)."),
            ("illegal_dumping", ComplaintStatus.OPEN, "Plastic dumped near the tank bund (synthetic)."),
            ("missed_pickup", ComplaintStatus.RESOLVED, "Pickup skipped during rain (synthetic)."),
            ("other", ComplaintStatus.CLOSED, "Request for a segregation awareness session (synthetic)."),
            ("overflowing_bin", ComplaintStatus.OPEN, "Market bin full after the weekly bazaar (synthetic)."),
            ("staff_behaviour", ComplaintStatus.RESOLVED, "Collector arrived late without notice (synthetic)."),
        ]
        done = (ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED)
        for i, (cat, status, desc) in enumerate(specs):
            code = ("VNP", "PCP", "NGT")[i % 3]
            hh = self.households[code][i]
            self.db.add(Complaint(
                village_id=self.villages[code].id, household_id=hh.id,
                raised_by=self.users["household"].id if hh.user_id else self.gp_admin(code).id,
                category=cat, description=desc, collection_point_id=self.points[code][i % 4].id, status=status,
                assigned_to=self.points[code][0].assigned_collector_id if status != ComplaintStatus.OPEN else None,
                resolution_note="Bin emptied and schedule confirmed (synthetic)." if status in done else None,
                resolved_at=self.now if status in done else None, data_origin=DataOrigin.DEMO_SEED,
            ))
        for code, *_ in VILLAGES:
            for cp in self.rng.sample(self.points[code], k=4):
                self.db.add(CollectionAssignment(collector_id=cp.assigned_collector_id, collection_point_id=cp.id, scheduled_date=today,
                                                 status=AssignmentStatus.PENDING, created_by=self.gp_admin(code).id))
        self.db.flush()

    def notifications(self) -> None:
        for code, *_ in VILLAGES:
            for cp in [p for p in self.points[code] if p.fill_percent and p.fill_percent >= 80][:3]:
                self.db.add(Notification(
                    user_id=self.gp_admin(code).id, type="bin_fill_alert", severity=Severity.WARNING,
                    title=f"{cp.code} is about {cp.fill_percent}% full (estimated)",
                    body="Estimated from days since the last pickup (synthetic demo data).",
                    entity_type="collection_point", entity_id=str(cp.id), link=f"/collection-points/{cp.id}", dedupe_key=f"fill:{cp.id}",
                ))
        self.db.flush()

    def run(self) -> dict:
        self.identity()
        self.waste_streams()
        self.households_and_points()
        self.collection_history()
        self.requests_complaints_assignments()
        self.notifications()
        from app.scripts import seed_operations  # devices, logistics, MRF, recovery, finance

        extra = seed_operations.run(self)
        return {
            "villages": len(self.villages),
            "collection_points": sum(len(p) for p in self.points.values()),
            "households": sum(len(h) for h in self.households.values()),
            "collection_events": self.n_events,
            **extra,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SYNTHETIC demo data")
    parser.add_argument("--reset", action="store_true", help="Delete existing operational data first")
    args = parser.parse_args()
    ensure_safe()
    with SessionLocal() as db:
        if args.reset:
            reset(db)
        elif db.scalar(select(User.id).limit(1)):
            raise SystemExit("Database already has users. Re-run with --reset to replace them with demo data.")
        summary = Seeder(db).run()
        db.commit()
    try:
        from app.iot.mqtt_auth import write_passwd_file_from_db

        write_passwd_file_from_db()
    except Exception as exc:  # noqa: BLE001
        print(f"warning: could not write MQTT credentials file: {exc}")
    print("Seeded SYNTHETIC demo data:", summary)
    print(f"Demo password for every account (development only): {DEMO_PASSWORD}")
    for email, role, label in DEMO_ACCOUNTS:
        print(f"  {role:<13} {email:<38} {label}")


if __name__ == "__main__":
    main()
