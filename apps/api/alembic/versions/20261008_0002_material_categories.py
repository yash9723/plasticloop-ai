"""material categories (reference data)

Revision ID: 0002_material_categories
Revises: b388bff0944f
Create Date: 2026-10-08

MRF/PWMU material taxonomy used for sorting and batches. Multi-layer packaging is tracked as its own category and
starts as "suspected": verification needs evidence attached to a batch, never a visual guess.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_material_categories"
down_revision: str | None = "b388bff0944f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = [
    # code, label, hi, te, is_mlp, is_unsorted, recoverable, needs_evidence
    ("mixed_unsorted", "Mixed / unsorted intake", "मिश्रित / बिना छँटा", "కలగలిసిన / వేరు చేయనిది", False, True, True, False),
    ("rigid_plastic", "Rigid plastic", "कठोर प्लास्टिक", "గట్టి ప్లాస్టిక్", False, False, True, False),
    ("flexible_plastic", "Flexible plastic (mono-layer film)", "लचीला प्लास्टिक (एकल परत)", "మెత్తని ప్లాస్టిక్ (ఒకే పొర)", False, False, True, False),
    ("suspected_mlp", "Multi-layer packaging (MLP)", "बहु-परत पैकेजिंग (MLP)", "బహుళ-పొర ప్యాకేజింగ్ (MLP)", True, False, True, True),
    ("paper_cardboard", "Paper & cardboard", "कागज़ और गत्ता", "కాగితం & అట్టపెట్టె", False, False, True, False),
    ("metal", "Metal", "धातु", "లోహం", False, False, True, False),
    ("nonrecoverable", "Non-recoverable residue", "अप्राप्य अवशेष", "తిరిగి పొందలేని అవశేషం", False, False, False, False),
    ("contamination_rejects", "Contamination / rejects", "दूषित / अस्वीकृत", "కలుషితం / తిరస్కరించినవి", False, False, False, False),
]


def upgrade() -> None:
    table = sa.table(
        "material_categories",
        sa.column("id", sa.UUID()),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("labels", postgresql.JSONB),
        sa.column("is_mlp", sa.Boolean),
        sa.column("is_unsorted", sa.Boolean),
        sa.column("recoverable", sa.Boolean),
        sa.column("requires_evidence_for_verification", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_URL, f"plasticloop:material_category:{code}"),
                "code": code,
                "label": label,
                "labels": {"hi": hi, "te": te},
                "is_mlp": mlp,
                "is_unsorted": unsorted,
                "recoverable": recoverable,
                "requires_evidence_for_verification": evidence,
                "sort_order": i,
            }
            for i, (code, label, hi, te, mlp, unsorted, recoverable, evidence) in enumerate(CATEGORIES)
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM material_categories WHERE code IN (%s)" % ", ".join(f"'{c[0]}'" for c in CATEGORIES))
