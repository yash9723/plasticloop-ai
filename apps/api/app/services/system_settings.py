"""Operational thresholds and cost assumptions. Defaults live in code; admins override them in `system_settings`."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting

# (default, description). Money in paise. Every cost value is an ASSUMPTION until replaced with local figures.
SETTINGS_SPEC: dict[str, tuple[Any, str]] = {
    "fill_alert_percent": (80, "Bin fill level (%) that triggers a fill alert"),
    "low_battery_percent": (20, "Device battery (%) that triggers a low-battery alert"),
    "device_offline_after_minutes": (30, "Minutes without telemetry before a device is marked offline"),
    "pickup_overdue_hours": (48, "Hours before an open pickup request is flagged overdue"),
    "max_collection_weight_kg": (500, "Upper bound for a single manually entered collection (kg)"),
    "mass_balance_tolerance_kg": (0.5, "Absolute mass-balance difference tolerated before flagging (kg)"),
    "mass_balance_tolerance_percent": (1.0, "Relative mass-balance difference tolerated before flagging (%)"),
    "transfer_discrepancy_tolerance_percent": (2.0, "Dispatch vs receipt difference tolerated before flagging (%)"),
    "vision_confidence_threshold": (0.70, "Below this score a classification is marked low-confidence"),
    "routing_avg_speed_kmph": (25, "Assumed average rural road speed for duration estimates"),
    "service_time_per_stop_min": (5, "Assumed handling time per collection stop (minutes)"),
    "route_cost_per_km_paise": (1500, "ASSUMPTION: vehicle operating cost per km (paise) for route cost estimates"),
    "labor_cost_per_hour_paise": (6000, "ASSUMPTION: collection labour cost per hour (paise)"),
    "inventory_aging_alert_days": (30, "Days in storage before a batch is flagged as awaiting processing"),
}


def get_all(db: Session) -> dict[str, Any]:
    values = {k: v[0] for k, v in SETTINGS_SPEC.items()}
    for row in db.scalars(select(SystemSetting).where(SystemSetting.key.in_(SETTINGS_SPEC))):
        values[row.key] = row.value
    return values


def get_value(db: Session, key: str) -> Any:
    row = db.get(SystemSetting, key)
    return row.value if row is not None else SETTINGS_SPEC[key][0]
