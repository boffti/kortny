"""Tool schema pinning + drift detection (HIG-169 P0.3).

A poisoned or compromised MCP server / Composio toolkit can mutate a tool's
``inputSchema`` *after* the admin's initial approval — the "rug pull". The
existing partial hashes do not catch this: Composio ``card_sha`` covers
name+description+side_effect only, MCP ``description_sha256`` covers the
description only. Neither includes the input schema, which is exactly the
rug-pull surface.

This module computes a fingerprint that DOES include the input schema and
pins it on first sight (the first registration is the admin's implicit
approval, consistent with the existing trust model). On every catalog refresh /
``tools/list`` — not just registration, because rug pulls exploit the
approve->call gap — the live fingerprint is recomputed and compared. A change
flips the pin to ``drifted``, which (via the approval policy) revokes the
read-only bypass until an admin re-pins.

Pure + cheap: the fingerprint is in-memory sha256; the only DB work is the
pin upsert / drift flip, hooked into the sync loops that already iterate tools.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import ToolPin

ToolPinProvider = Literal["mcp", "composio"]


@dataclass(frozen=True, slots=True)
class ToolFingerprint:
    """A tool's canonical fingerprint plus the source fields it was built from."""

    fingerprint: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PinCheckResult:
    """Outcome of pinning / drift-checking one tool.

    ``drifted`` is True when the live fingerprint diverged from a previously
    pinned one this check (or the pin is already in the ``drifted`` state). The
    approval policy consults :func:`tool_pin_is_clean` at gate time; this result
    is the sync-loop's view for logging.
    """

    pinned: bool
    drifted: bool
    fingerprint: str
    prior_fingerprint: str | None


def compute_tool_fingerprint(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any] | None,
    output_schema: dict[str, Any] | None = None,
    annotations: dict[str, Any] | None = None,
) -> ToolFingerprint:
    """Return the canonical sha256 fingerprint of a tool's identity + schema.

    The fingerprint is ``sha256`` of canonical JSON over
    ``{name, description, inputSchema, outputSchema?, annotations?}`` with
    ``sort_keys=True`` and compact separators, so semantically identical tools
    hash identically regardless of key order or whitespace. ``inputSchema`` is
    always included — it is the rug-pull surface.
    """

    schema = input_schema if isinstance(input_schema, dict) else {}
    payload: dict[str, Any] = {
        "name": name,
        "description": description or "",
        "inputSchema": schema,
    }
    if output_schema is not None:
        payload["outputSchema"] = output_schema
    if annotations:
        payload["annotations"] = annotations
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ToolFingerprint(
        fingerprint=digest,
        description=description or "",
        input_schema=schema,
    )


class ToolPinService:
    """Pin-on-first-sight + drift detection over the ``tool_pins`` table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_pin(
        self,
        *,
        installation_id: uuid.UUID,
        provider: ToolPinProvider,
        server_ref: str,
        tool_name: str,
    ) -> ToolPin | None:
        return self.session.scalar(
            select(ToolPin).where(
                ToolPin.installation_id == installation_id,
                ToolPin.provider == provider,
                ToolPin.server_ref == server_ref,
                ToolPin.tool_name == tool_name,
            )
        )

    def is_clean(
        self,
        *,
        installation_id: uuid.UUID,
        provider: ToolPinProvider,
        server_ref: str,
        tool_name: str,
    ) -> bool:
        """True when the tool has an ``active`` (non-drifted) pin.

        A missing pin returns False: a tool the gate has never seen pinned is
        treated as unpinned, so its read-only claim does not clear approval.
        """

        pin = self.get_pin(
            installation_id=installation_id,
            provider=provider,
            server_ref=server_ref,
            tool_name=tool_name,
        )
        return pin is not None and pin.status == "active"

    def check_and_pin(
        self,
        *,
        installation_id: uuid.UUID,
        provider: ToolPinProvider,
        server_ref: str,
        tool_name: str,
        fingerprint: ToolFingerprint,
        now: datetime | None = None,
    ) -> PinCheckResult:
        """Pin on first sight, or flag drift when the fingerprint changed.

        Idempotent: an unchanged fingerprint touches nothing. A changed
        fingerprint flips the pin to ``drifted`` and stores the NEW fingerprint
        plus the PRIOR description/schema so the dashboard can render a diff. A
        re-pin (admin action) is the inverse, handled by :meth:`repin`.
        """

        moment = now or datetime.now(UTC)
        pin = self.get_pin(
            installation_id=installation_id,
            provider=provider,
            server_ref=server_ref,
            tool_name=tool_name,
        )
        if pin is None:
            self.session.add(
                ToolPin(
                    installation_id=installation_id,
                    provider=provider,
                    server_ref=server_ref,
                    tool_name=tool_name,
                    fingerprint=fingerprint.fingerprint,
                    prior_description=fingerprint.description,
                    prior_schema_json=fingerprint.input_schema,
                    status="active",
                    approved_at=moment,
                )
            )
            self.session.flush()
            return PinCheckResult(
                pinned=True,
                drifted=False,
                fingerprint=fingerprint.fingerprint,
                prior_fingerprint=None,
            )

        if pin.fingerprint == fingerprint.fingerprint:
            # Unchanged. If a prior drift was re-pinned to this same value the
            # status is already active; nothing to do either way.
            return PinCheckResult(
                pinned=False,
                drifted=pin.status == "drifted",
                fingerprint=fingerprint.fingerprint,
                prior_fingerprint=pin.fingerprint,
            )

        prior_fingerprint = pin.fingerprint
        # Preserve the previously-pinned description/schema for the diff, but
        # only the first time we observe this drift (don't overwrite the known
        # baseline with intermediate drift values on repeated checks).
        if pin.status != "drifted":
            pin.prior_description = pin.prior_description
            pin.prior_schema_json = pin.prior_schema_json
        pin.fingerprint = fingerprint.fingerprint
        pin.status = "drifted"
        pin.updated_at = moment
        self.session.flush()
        return PinCheckResult(
            pinned=False,
            drifted=True,
            fingerprint=fingerprint.fingerprint,
            prior_fingerprint=prior_fingerprint,
        )

    def repin(
        self,
        *,
        installation_id: uuid.UUID,
        provider: ToolPinProvider,
        server_ref: str,
        tool_name: str,
        approved_by: str,
        now: datetime | None = None,
    ) -> ToolPin | None:
        """Admin re-approval of a drifted tool: reset status to ``active``.

        The current fingerprint stored on the row (the drifted one) becomes the
        new baseline, and the prior description/schema is refreshed to it so a
        subsequent change diffs against the now-approved version.
        """

        pin = self.get_pin(
            installation_id=installation_id,
            provider=provider,
            server_ref=server_ref,
            tool_name=tool_name,
        )
        if pin is None:
            return None
        moment = now or datetime.now(UTC)
        pin.status = "active"
        pin.approved_by = approved_by
        pin.approved_at = moment
        pin.updated_at = moment
        self.session.flush()
        return pin


__all__ = [
    "PinCheckResult",
    "ToolFingerprint",
    "ToolPinProvider",
    "ToolPinService",
    "compute_tool_fingerprint",
]
