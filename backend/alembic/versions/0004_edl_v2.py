"""EDL v2 (segments) and clip revision history

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06

"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "clip_revisions",
        sa.Column(
            "clip_id", sa.Uuid(), sa.ForeignKey("clips.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("edl", postgresql.JSONB(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    _rewrite(_to_v2)


def downgrade() -> None:
    _rewrite(_to_v1)
    op.drop_table("clip_revisions")
    op.drop_column("clips", "revision")


def _rewrite(convert) -> None:
    """Convert the EDL of every clip and of every export job's payload snapshot."""
    bind = op.get_bind()
    for clip_id, edl in bind.execute(sa.text("SELECT id, edl FROM clips")).all():
        bind.execute(
            sa.text("UPDATE clips SET edl = CAST(:edl AS jsonb) WHERE id = :id"),
            {"id": clip_id, "edl": json.dumps(convert(edl))},
        )
    jobs = bind.execute(sa.text("SELECT id, payload FROM jobs WHERE type = 'export'")).all()
    for job_id, payload in jobs:
        if "edl" in payload:
            payload = {**payload, "edl": convert(payload["edl"])}
            bind.execute(
                sa.text("UPDATE jobs SET payload = CAST(:payload AS jsonb) WHERE id = :id"),
                {"id": job_id, "payload": json.dumps(payload)},
            )


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _to_v2(edl: dict) -> dict:
    if edl.get("version") == 2:
        return edl
    out = {k: v for k, v in edl.items() if k != "ranges"}
    out["version"] = 2
    out["segments"] = [
        {"id": _new_id(), "kind": "video", "start": r["start"], "end": r["end"]}
        for r in edl["ranges"]
    ]
    out["overlays"] = [{**o, "id": o.get("id") or _new_id()} for o in edl.get("overlays", [])]
    return out


def _to_v1(edl: dict) -> dict:
    """Best effort: the clip-video segments, in source order and merged, become ranges."""
    if edl.get("version") != 2:
        return edl
    spans = sorted(
        (s["start"], s["end"])
        for s in edl["segments"]
        if s.get("kind") == "video" and s.get("media") is None
    )
    ranges: list[dict] = []
    for start, end in spans:
        if ranges and start <= ranges[-1]["end"]:
            ranges[-1]["end"] = max(ranges[-1]["end"], end)
        else:
            ranges.append({"start": start, "end": end})
    keep = ("aspect", "crop", "split_screen", "tracking", "captions", "music")
    out = {k: edl[k] for k in keep if k in edl}
    out["ranges"] = ranges
    out["overlays"] = [{k: v for k, v in o.items() if k != "id"} for o in edl.get("overlays", [])]
    return out
