"""Deterministic autonomy ladder for tool calls (HIG-223).

Kortny acts like a coworker, not a permission bot. This module classifies a
planned tool call into one of three autonomy tiers from *static metadata plus
argument inspection only* — no LLM, no network, no side effects:

* ``free``     — reads, sandbox execution, local artifact generation. Auto, no
  prompt, no audit.
* ``implicit`` — external create/update. Auto, but every auto-approval records a
  ``tool_autonomy_decision`` audit event.
* ``explicit`` — irreversible / outward / bulk mutations (deletes, drops, sends,
  publishes, deploys, payments). Routed to the existing Slack reaction approval
  flow.

The workspace-default + per-channel autonomy *level* (``conservative`` /
``balanced`` / ``autonomous``) then maps tier x level to a concrete approval
requirement in :mod:`kortny.approvals`. This module owns the *risk* half of that
decision; ``kortny.approvals`` owns the *policy* half.

Design notes:
* Conservative about unknowns: an unknown write-ish tool is ``implicit`` (surfaced
  + audited at balanced, gated at conservative), never silently ``free``.
* Destructive metadata is always ``explicit`` regardless of arguments.
* SQL/HTTP verb parsing is leading-token based and CTE-aware (``WITH ... DELETE``
  escalates) so a benign-looking wrapper cannot smuggle a destructive verb.

TODO(HIG-223 v2): undo-first (act-then-offer-undo) is out of scope for v1. When
added, Tier-1 implicit ops should capture an inverse action and surface an
``undo`` affordance instead of (or alongside) the audit event.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kortny.tools.catalog import ToolMetadata

DEFAULT_AUTONOMY_LEVEL = "balanced"


class AutonomyTier(StrEnum):
    """Risk tier a tool call falls into, independent of the autonomy level."""

    free = "free"
    implicit = "implicit"
    explicit = "explicit"


class AutonomyLevel(StrEnum):
    """Operator-chosen autonomy posture, scoped workspace/channel."""

    conservative = "conservative"
    balanced = "balanced"
    autonomous = "autonomous"


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Deterministic risk classification for one planned tool call."""

    tier: AutonomyTier
    reasons: tuple[str, ...]


# --- Verb vocabularies -------------------------------------------------------

# SQL leading verbs. Free verbs never mutate; implicit verbs mutate but are
# reversible-ish; explicit verbs are destructive / schema-altering.
SQL_FREE_VERBS = frozenset({"select", "explain", "show", "with"})
SQL_IMPLICIT_VERBS = frozenset({"insert", "update", "upsert", "merge", "replace"})
SQL_EXPLICIT_VERBS = frozenset(
    {"delete", "drop", "truncate", "alter", "grant", "revoke"}
)

# HTTP methods by semantic risk.
HTTP_FREE_METHODS = frozenset({"get", "head", "options"})
HTTP_IMPLICIT_METHODS = frozenset({"post", "put", "patch"})
HTTP_EXPLICIT_METHODS = frozenset({"delete"})

# Outward / irreversible capability + verb signals that force explicit.
OUTWARD_SIGNALS = frozenset(
    {
        "send",
        "email",
        "publish",
        "deploy",
        "payment",
        "pay",
        "charge",
        "invoice",
        "broadcast",
        "tweet",
        "post_public",
    }
)
DESTRUCTIVE_SIGNALS = frozenset(
    {"delete", "remove", "destroy", "drop", "purge", "wipe", "truncate"}
)

# Composio / generic write verbs that map to the implicit (create/update) base.
WRITE_SIGNALS = frozenset(
    {
        "create",
        "update",
        "add",
        "insert",
        "set",
        "write",
        "edit",
        "modify",
        "upsert",
        "append",
        "enable",
        "disable",
        "move",
        "archive",
        "invite",
        "submit",
    }
)

# Bulk signals escalate one tier.
BULK_LITERALS = frozenset({"all", "everyone", "*", "%"})
BULK_KEY_HINTS = ("ids", "_ids", "bulk", "batch", "all_", "filter", "where")

_SQL_COMMENT_RE = re.compile(r"(--[^\n]*\n?)|(/\*.*?\*/)", re.DOTALL)
_LEADING_TOKEN_RE = re.compile(r"[a-zA-Z_]+")
_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _escalate(tier: AutonomyTier) -> AutonomyTier:
    if tier is AutonomyTier.free:
        return AutonomyTier.implicit
    return AutonomyTier.explicit


def _max_tier(left: AutonomyTier, right: AutonomyTier) -> AutonomyTier:
    order = {AutonomyTier.free: 0, AutonomyTier.implicit: 1, AutonomyTier.explicit: 2}
    return left if order[left] >= order[right] else right


def _words(text: str) -> set[str]:
    return {part for part in _WORD_SPLIT_RE.split(text.casefold()) if part}


def _looks_like_sql(value: str) -> bool:
    stripped = _SQL_COMMENT_RE.sub(" ", value).strip()
    if not stripped:
        return False
    match = _LEADING_TOKEN_RE.match(stripped)
    if match is None:
        return False
    head = match.group(0).casefold()
    return (
        head in SQL_FREE_VERBS
        or head in SQL_IMPLICIT_VERBS
        or head in SQL_EXPLICIT_VERBS
    )


def _sql_tier(value: str) -> tuple[AutonomyTier, tuple[str, ...]] | None:
    """Classify a SQL-bearing string by its first meaningful verb.

    Strips leading comments/whitespace, reads the leading token, and — when that
    token is a CTE (``WITH``) — scans the remaining keywords for the first real
    mutation verb. Ambiguous CTEs (no inner verb recognised) escalate to explicit
    so a hidden ``DELETE`` cannot ride in on a benign ``WITH``.
    """

    cleaned = _SQL_COMMENT_RE.sub(" ", value).strip()
    match = _LEADING_TOKEN_RE.match(cleaned)
    if match is None:
        return None
    head = match.group(0).casefold()

    if head in SQL_EXPLICIT_VERBS:
        return AutonomyTier.explicit, (f"sql_verb:{head}",)
    if head in SQL_IMPLICIT_VERBS:
        return AutonomyTier.implicit, (f"sql_verb:{head}",)
    if head == "with":
        return _sql_cte_tier(cleaned)
    if head in SQL_FREE_VERBS:
        return AutonomyTier.free, (f"sql_verb:{head}",)
    return None


def _sql_cte_tier(cleaned: str) -> tuple[AutonomyTier, tuple[str, ...]]:
    """Classify a ``WITH`` CTE by the strongest mutation verb anywhere in it.

    CTE bodies nest reads inside parentheses, so a simple leading-verb scan is
    unreliable. Instead we look for the strongest mutation keyword present:
    any explicit verb -> explicit; else any implicit verb -> implicit; else the
    CTE only feeds a read -> free. Unknown/ambiguous ``WITH`` (no keyword at all
    after the CTE name) escalates to explicit to stay safe.
    """

    tokens = {tok for tok in _WORD_SPLIT_RE.split(cleaned.casefold()) if tok}
    explicit_hits = tokens & SQL_EXPLICIT_VERBS
    if explicit_hits:
        return AutonomyTier.explicit, ("sql_cte_verb:" + sorted(explicit_hits)[0],)
    implicit_hits = tokens & SQL_IMPLICIT_VERBS
    if implicit_hits:
        return AutonomyTier.implicit, ("sql_cte_verb:" + sorted(implicit_hits)[0],)
    if "select" in tokens:
        return AutonomyTier.free, ("sql_cte_verb:select",)
    return AutonomyTier.explicit, ("sql_cte_ambiguous",)


def _http_tier(value: str) -> tuple[AutonomyTier, tuple[str, ...]] | None:
    token = value.strip().casefold()
    if token in HTTP_EXPLICIT_METHODS:
        return AutonomyTier.explicit, (f"http_method:{token}",)
    if token in HTTP_IMPLICIT_METHODS:
        return AutonomyTier.implicit, (f"http_method:{token}",)
    if token in HTTP_FREE_METHODS:
        return AutonomyTier.free, (f"http_method:{token}",)
    return None


def _looks_like_http_method_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized in {"method", "http_method", "verb", "request_method"}


def _bulk_signal(args: Mapping[str, Any]) -> str | None:
    for key, value in args.items():
        lowered = key.casefold()
        if any(hint in lowered for hint in BULK_KEY_HINTS):
            return f"bulk_arg:{key}"
        if isinstance(value, (list, tuple, set)) and len(value) > 1:
            return f"bulk_collection:{key}"
        if isinstance(value, str) and value.strip().casefold() in BULK_LITERALS:
            return f"bulk_literal:{key}"
    return None


def classify_tool_risk(
    metadata: ToolMetadata,
    args: Mapping[str, Any],
) -> RiskAssessment:
    """Classify a planned tool call into an :class:`AutonomyTier`.

    Pure and deterministic: metadata side_effect/capabilities form the base tier,
    then string arguments are inspected for SQL/HTTP verbs and outward/destructive
    signals, and bulk signals escalate one tier. Unknown write-ish tools default
    to ``implicit``; ``destructive`` metadata is always ``explicit``.
    """

    reasons: list[str] = []

    # --- Base tier from metadata ---------------------------------------------
    side_effect = metadata.side_effect
    capability_text = " ".join((metadata.name, *metadata.capabilities))
    capability_words = _words(capability_text)

    if side_effect == "destructive":
        base = AutonomyTier.explicit
        reasons.append("metadata_side_effect:destructive")
    elif side_effect == "write":
        base = AutonomyTier.implicit
        reasons.append("metadata_side_effect:write")
    else:
        base = AutonomyTier.free
        reasons.append("metadata_side_effect:read")

    # Outward / irreversible capability words always force explicit.
    outward_hits = capability_words & OUTWARD_SIGNALS
    if outward_hits:
        base = AutonomyTier.explicit
        reasons.append("capability_outward:" + ",".join(sorted(outward_hits)))
    destructive_hits = capability_words & DESTRUCTIVE_SIGNALS
    if destructive_hits:
        base = AutonomyTier.explicit
        reasons.append("capability_destructive:" + ",".join(sorted(destructive_hits)))

    # A read tool with no write capability words stays free; if it carries write
    # words, treat it as at-least implicit (conservative about mislabelled reads).
    if base is AutonomyTier.free and capability_words & WRITE_SIGNALS:
        base = AutonomyTier.implicit
        reasons.append("capability_write_hint")

    tier = base

    # --- Argument inspection -------------------------------------------------
    for key, value in args.items():
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        if _looks_like_http_method_key(key):
            http = _http_tier(text)
            if http is not None:
                http_tier, http_reasons = http
                tier = _max_tier(tier, http_tier)
                reasons.extend(http_reasons)
                continue
        if _looks_like_sql(text):
            sql = _sql_tier(text)
            if sql is not None:
                sql_tier, sql_reasons = sql
                tier = _max_tier(tier, sql_tier)
                reasons.extend(sql_reasons)
                continue
        words = _words(text)
        if words & DESTRUCTIVE_SIGNALS:
            tier = AutonomyTier.explicit
            reasons.append("arg_destructive:" + key)
        elif words & OUTWARD_SIGNALS:
            tier = AutonomyTier.explicit
            reasons.append("arg_outward:" + key)

    # --- Bulk escalation -----------------------------------------------------
    bulk_reason = _bulk_signal(args)
    if bulk_reason is not None and tier is not AutonomyTier.free:
        escalated = _escalate(tier)
        if escalated is not tier:
            reasons.append("bulk_escalation:" + bulk_reason)
            tier = escalated

    return RiskAssessment(tier=tier, reasons=tuple(reasons))


def resolve_autonomy_level(
    *,
    channel_level: str | None,
    workspace_level: str | None,
    default_level: str = DEFAULT_AUTONOMY_LEVEL,
) -> AutonomyLevel:
    """Resolve the effective level: channel override -> workspace -> default.

    Narrowest scope wins, mirroring the observe-policy resolution pattern.
    """

    for candidate in (channel_level, workspace_level, default_level):
        level = _coerce_level(candidate)
        if level is not None:
            return level
    return AutonomyLevel.balanced


def _coerce_level(value: str | None) -> AutonomyLevel | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    try:
        return AutonomyLevel(normalized)
    except ValueError:
        return None


__all__ = [
    "DEFAULT_AUTONOMY_LEVEL",
    "AutonomyTier",
    "AutonomyLevel",
    "RiskAssessment",
    "classify_tool_risk",
    "resolve_autonomy_level",
]
