"""Evidence-backed Witness opportunity candidates.

This module intentionally stops at candidate persistence. Delivery, feedback UI,
and public proactive posting are separate policy slices.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    ObserveChannelProfile,
    SlackChannelMembership,
    Task,
    WitnessOpportunityCandidate,
)

WITNESS_OPPORTUNITY_CANDIDATES_PROJECTED_MESSAGE = (
    "witness_opportunity_candidates_projected"
)
MAX_PROFILE_OPPORTUNITIES = 5
MAX_TASK_RESPONSE_OPPORTUNITIES = 5
ELIGIBLE_STATUSES = ("candidate",)

_WHITESPACE_RE = re.compile(r"\s+")
_BULLET_RE = re.compile("^\\s*(?:[-*]|\\u2022|\\d+[.)])\\s+(.+)")
_DATA_QUALITY_RE = re.compile(
    r"\b(csv|file|placeholder|missing|stale|format|data quality|reconcile|error|"
    r"failed|broken|invalid|quality|diff)\b",
    re.I,
)
_ARTIFACT_RE = re.compile(
    r"\b(doc|document|deck|brief|one[- ]pager|memo|report|pdf|artifact|draft|"
    r"page|write|revise)\b",
    re.I,
)
_DECISION_RE = re.compile(
    r"\b(decision|unresolved|open question|follow[- ]?up|pending|blocker|owner|"
    r"next step)\b",
    re.I,
)
_RECURRING_RE = re.compile(
    r"\b(every|daily|weekly|monthly|recurring|repeat|periodic|cadence|schedule|"
    r"heartbeat|monitor)\b",
    re.I,
)
_PROJECT_STATUS_RE = re.compile(
    r"\b(project|roadmap|status|milestone|launch|workstream|tracker)\b",
    re.I,
)
_WORKFLOW_RE = re.compile(
    r"\b(workflow|automate|automation|process|handoff|review|summari[sz]e|"
    r"compare|check)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class WitnessOpportunityCandidateResult:
    """Result from projecting candidate rows from one source."""

    created_count: int
    updated_count: int
    skipped_count: int
    candidate_ids: tuple[str, ...]

    @property
    def total_count(self) -> int:
        return self.created_count + self.updated_count


class WitnessOpportunityService:
    """Create and query proactive opportunity candidates."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def project_from_channel_profile(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
        profile: ObserveChannelProfile,
    ) -> WitnessOpportunityCandidateResult:
        """Create/update candidates from profile help opportunities."""

        extraction = _semantic_extraction(profile)
        opportunities = _bounded_text_list(extraction.get("help_opportunities"), limit=5)
        if not opportunities:
            return WitnessOpportunityCandidateResult(
                created_count=0,
                updated_count=0,
                skipped_count=1,
                candidate_ids=(),
            )

        now = datetime.now(UTC)
        evidence_items = _evidence_items(
            task=task,
            membership=membership,
            profile=profile,
            extraction=extraction,
        )
        confidence_score = _confidence_score(
            extraction.get("confidence"),
            profile.confidence_score,
        )
        confidence_reason = _confidence_reason(profile, extraction.get("confidence"))
        scope_type, scope_id = _scope_for_membership(membership)

        created_count = 0
        updated_count = 0
        skipped_count = 0
        candidate_ids: list[str] = []

        for opportunity in opportunities[:MAX_PROFILE_OPPORTUNITIES]:
            candidate_type = _candidate_type(opportunity)
            dedupe_key = _dedupe_key(
                channel_id=membership.channel_id,
                candidate_type=candidate_type,
                opportunity=opportunity,
            )
            existing = self._find_existing(
                installation_id=task.installation_id,
                scope_type=scope_type,
                scope_id=scope_id,
                candidate_type=candidate_type,
                dedupe_key=dedupe_key,
            )
            title = _title(opportunity, candidate_type)
            summary = _summary(opportunity, membership=membership)
            metadata = {
                "source": "channel_profile_help_opportunity",
                "profile_version": profile.profile_version,
                "channel_name": membership.channel_name,
                "semantic_confidence": extraction.get("confidence"),
                "message_count": profile.message_count,
                "file_count": profile.file_count,
                "observed_range_start_ts": profile.observed_range_start_ts,
                "observed_range_end_ts": profile.observed_range_end_ts,
            }
            if existing is None:
                candidate = WitnessOpportunityCandidate(
                    installation_id=task.installation_id,
                    channel_id=membership.channel_id,
                    target_slack_user_id=None,
                    visibility_scope_type=scope_type,
                    visibility_scope_id=scope_id,
                    candidate_type=candidate_type,
                    title=title,
                    summary=summary,
                    suggested_action=_suggested_action(opportunity),
                    suggested_message=_suggested_message(
                        opportunity,
                        membership=membership,
                    ),
                    evidence_json=evidence_items,
                    source_type="channel_profile",
                    source_id=str(profile.id),
                    source_task_id=task.id,
                    source_profile_id=profile.id,
                    dedupe_key=dedupe_key,
                    confidence_score=confidence_score,
                    confidence_reason=confidence_reason,
                    status="candidate",
                    feedback_json={},
                    metadata_json=metadata,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(candidate)
                self.session.flush()
                created_count += 1
            else:
                candidate = existing
                candidate.title = title
                candidate.summary = summary
                candidate.suggested_action = _suggested_action(opportunity)
                candidate.suggested_message = _suggested_message(
                    opportunity,
                    membership=membership,
                )
                candidate.evidence_json = evidence_items
                candidate.source_id = str(profile.id)
                candidate.source_task_id = task.id
                candidate.source_profile_id = profile.id
                candidate.confidence_score = confidence_score
                candidate.confidence_reason = confidence_reason
                candidate.metadata_json = {
                    **(candidate.metadata_json or {}),
                    **metadata,
                    "last_reinforced_at": now.isoformat(),
                }
                candidate.updated_at = now
                self.session.flush()
                updated_count += 1

            candidate_ids.append(str(candidate.id))

        self.session.flush()
        return WitnessOpportunityCandidateResult(
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            candidate_ids=tuple(candidate_ids),
        )

    def project_from_task_response(
        self,
        *,
        task: Task,
        response_text: str,
    ) -> WitnessOpportunityCandidateResult:
        """Create/update candidates from a delivered answer's watch-for section."""

        opportunities = _task_response_opportunities(response_text)
        if not opportunities:
            return WitnessOpportunityCandidateResult(
                created_count=0,
                updated_count=0,
                skipped_count=1,
                candidate_ids=(),
            )

        membership = _membership_for_task(self.session, task)
        scope_type, scope_id = _scope_for_task(task, membership)
        if scope_id is None:
            return WitnessOpportunityCandidateResult(
                created_count=0,
                updated_count=0,
                skipped_count=1,
                candidate_ids=(),
            )

        now = datetime.now(UTC)
        channel_label = _channel_label(task, membership)
        channel_id = task.slack_channel_id or scope_id
        created_count = 0
        updated_count = 0
        candidate_ids: list[str] = []

        for opportunity in opportunities:
            candidate_type = _candidate_type(opportunity)
            dedupe_key = _dedupe_key(
                channel_id=channel_id,
                candidate_type=candidate_type,
                opportunity=opportunity,
            )
            existing = self._find_existing(
                installation_id=task.installation_id,
                scope_type=scope_type,
                scope_id=scope_id,
                candidate_type=candidate_type,
                dedupe_key=dedupe_key,
            )
            title = _title(opportunity, candidate_type)
            metadata = {
                "source": "task_watch_section",
                "channel_name": membership.channel_name if membership else None,
                "input": _bounded_text(task.input, 280),
                "response_chars": len(response_text),
            }
            evidence_items = _task_response_evidence(
                task=task,
                opportunity=opportunity,
                response_text=response_text,
                channel_id=channel_id,
            )
            if existing is None:
                candidate = WitnessOpportunityCandidate(
                    installation_id=task.installation_id,
                    channel_id=task.slack_channel_id,
                    target_slack_user_id=(
                        task.slack_user_id if scope_type == "dm" else None
                    ),
                    visibility_scope_type=scope_type,
                    visibility_scope_id=scope_id,
                    candidate_type=candidate_type,
                    title=title,
                    summary=_summary_for_label(
                        opportunity,
                        channel_label=channel_label,
                    ),
                    suggested_action=_suggested_action(opportunity),
                    suggested_message=_suggested_message_for_label(
                        opportunity,
                        channel_label=channel_label,
                    ),
                    evidence_json=evidence_items,
                    source_type="task_summary",
                    source_id=str(task.id),
                    source_task_id=task.id,
                    source_profile_id=None,
                    dedupe_key=dedupe_key,
                    confidence_score=Decimal("0.620"),
                    confidence_reason=(
                        "Derived from Kortny's completed answer for a "
                        "channel-profile/watch-for request."
                    ),
                    status="candidate",
                    feedback_json={},
                    metadata_json=metadata,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(candidate)
                self.session.flush()
                created_count += 1
            else:
                candidate = existing
                candidate.title = title
                candidate.summary = _summary_for_label(
                    opportunity,
                    channel_label=channel_label,
                )
                candidate.suggested_action = _suggested_action(opportunity)
                candidate.suggested_message = _suggested_message_for_label(
                    opportunity,
                    channel_label=channel_label,
                )
                candidate.evidence_json = evidence_items
                if candidate.source_type == "task_summary":
                    candidate.source_id = str(task.id)
                candidate.source_task_id = task.id
                candidate.confidence_score = max(
                    candidate.confidence_score or Decimal("0.000"),
                    Decimal("0.620"),
                )
                candidate.confidence_reason = (
                    "Reinforced by Kortny's completed answer for a "
                    "channel-profile/watch-for request."
                )
                candidate.metadata_json = {
                    **(candidate.metadata_json or {}),
                    **metadata,
                    "last_reinforced_at": now.isoformat(),
                }
                candidate.updated_at = now
                self.session.flush()
                updated_count += 1

            candidate_ids.append(str(candidate.id))

        self.session.flush()
        return WitnessOpportunityCandidateResult(
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=0,
            candidate_ids=tuple(candidate_ids),
        )

    def eligible_private_suggestions(
        self,
        *,
        installation_id: uuid.UUID,
        limit: int = 20,
        now: datetime | None = None,
    ) -> tuple[WitnessOpportunityCandidate, ...]:
        """Return currently eligible candidates for a future private DM sender."""

        observed_now = now or datetime.now(UTC)
        rows = self.session.scalars(
            select(WitnessOpportunityCandidate)
            .where(
                WitnessOpportunityCandidate.installation_id == installation_id,
                WitnessOpportunityCandidate.status.in_(ELIGIBLE_STATUSES),
                or_(
                    WitnessOpportunityCandidate.cooldown_until.is_(None),
                    WitnessOpportunityCandidate.cooldown_until <= observed_now,
                ),
            )
            .order_by(
                WitnessOpportunityCandidate.confidence_score.desc(),
                WitnessOpportunityCandidate.created_at.asc(),
            )
            .limit(limit)
        )
        return tuple(rows)

    def _find_existing(
        self,
        *,
        installation_id: uuid.UUID,
        scope_type: str,
        scope_id: str | None,
        candidate_type: str,
        dedupe_key: str,
    ) -> WitnessOpportunityCandidate | None:
        return self.session.scalar(
            select(WitnessOpportunityCandidate).where(
                WitnessOpportunityCandidate.installation_id == installation_id,
                WitnessOpportunityCandidate.visibility_scope_type == scope_type,
                WitnessOpportunityCandidate.visibility_scope_id == scope_id,
                WitnessOpportunityCandidate.candidate_type == candidate_type,
                WitnessOpportunityCandidate.dedupe_key == dedupe_key,
            )
        )


def _semantic_extraction(profile: ObserveChannelProfile) -> dict[str, Any]:
    profile_payload = profile.profile_json if isinstance(profile.profile_json, dict) else {}
    extraction = profile_payload.get("semantic_extraction")
    if isinstance(extraction, dict):
        return extraction
    metadata = profile.metadata_json if isinstance(profile.metadata_json, dict) else {}
    extraction = metadata.get("semantic_extraction")
    return extraction if isinstance(extraction, dict) else {}


def _evidence_items(
    *,
    task: Task,
    membership: SlackChannelMembership,
    profile: ObserveChannelProfile,
    extraction: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "type": "channel_profile",
            "profile_id": str(profile.id),
            "profile_version": profile.profile_version,
            "source_task_id": str(task.id),
            "channel_id": membership.channel_id,
            "summary": _bounded_text(profile.summary or "", 500),
        }
    ]
    evidence = _bounded_text_list(extraction.get("evidence"), limit=5)
    for snippet in evidence:
        items.append(
            {
                "type": "semantic_evidence",
                "snippet": snippet,
                "profile_id": str(profile.id),
                "channel_id": membership.channel_id,
            }
        )
    if isinstance(profile.evidence_refs_json, list):
        for ref in profile.evidence_refs_json[:5]:
            if isinstance(ref, dict):
                items.append({"type": "profile_ref", **ref})
    return items[:10]


def _candidate_type(opportunity: str) -> str:
    if _DATA_QUALITY_RE.search(opportunity):
        return "data_quality_issue"
    if _ARTIFACT_RE.search(opportunity):
        return "artifact_followup"
    if _DECISION_RE.search(opportunity):
        return "unresolved_decision"
    if _RECURRING_RE.search(opportunity):
        return "recurring_check"
    if _PROJECT_STATUS_RE.search(opportunity):
        return "project_status_gap"
    if _WORKFLOW_RE.search(opportunity):
        return "workflow_gap"
    return "general_help"


def _scope_for_membership(membership: SlackChannelMembership) -> tuple[str, str]:
    channel_type = (membership.channel_type or "").lower()
    if channel_type in {"private_channel", "group", "mpim"}:
        return "private_channel", membership.channel_id
    return "channel", membership.channel_id


def _membership_for_task(
    session: Session,
    task: Task,
) -> SlackChannelMembership | None:
    if not task.slack_channel_id or task.slack_channel_id.startswith("D"):
        return None
    return session.scalar(
        select(SlackChannelMembership).where(
            SlackChannelMembership.installation_id == task.installation_id,
            SlackChannelMembership.channel_id == task.slack_channel_id,
        )
    )


def _scope_for_task(
    task: Task,
    membership: SlackChannelMembership | None,
) -> tuple[str, str | None]:
    if membership is not None:
        return _scope_for_membership(membership)
    if task.slack_channel_id and task.slack_channel_id.startswith("D"):
        return "dm", task.slack_channel_id
    if task.slack_channel_id:
        return "channel", task.slack_channel_id
    if task.slack_user_id:
        return "user", task.slack_user_id
    return "workspace", None


def _channel_label(
    task: Task,
    membership: SlackChannelMembership | None,
) -> str:
    if membership is not None and membership.channel_name:
        return f"#{membership.channel_name}"
    if task.slack_channel_id and task.slack_channel_id.startswith("D"):
        return "this DM"
    if task.slack_channel_id:
        return task.slack_channel_id
    return "this workspace"


def _confidence_score(
    semantic_confidence: object,
    profile_confidence_score: Decimal | None,
) -> Decimal:
    base = profile_confidence_score or Decimal("0.500")
    if semantic_confidence == "high":
        return max(base, Decimal("0.750"))
    if semantic_confidence == "medium":
        return max(base, Decimal("0.600"))
    if semantic_confidence == "low":
        return min(base, Decimal("0.450"))
    return base


def _confidence_reason(
    profile: ObserveChannelProfile,
    semantic_confidence: object,
) -> str:
    semantic = semantic_confidence if isinstance(semantic_confidence, str) else "unknown"
    profile_reason = profile.confidence_reason or "Channel profile generated a help opportunity."
    return f"{profile_reason} Semantic extraction confidence: {semantic}."


def _dedupe_key(
    *,
    channel_id: str,
    candidate_type: str,
    opportunity: str,
) -> str:
    normalized = _normalize_for_key(f"{channel_id}:{candidate_type}:{opportunity}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _normalize_for_key(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip().lower())


def _title(opportunity: str, candidate_type: str) -> str:
    prefix = {
        "workflow_gap": "Workflow opportunity",
        "artifact_followup": "Artifact follow-up",
        "unresolved_decision": "Unresolved decision",
        "data_quality_issue": "Data quality watch",
        "recurring_check": "Recurring check",
        "project_status_gap": "Project status gap",
        "general_help": "Help opportunity",
    }[candidate_type]
    return _bounded_text(f"{prefix}: {opportunity}", 140)


def _summary(
    opportunity: str,
    *,
    membership: SlackChannelMembership,
) -> str:
    channel = f"#{membership.channel_name}" if membership.channel_name else membership.channel_id
    return _summary_for_label(opportunity, channel_label=channel)


def _summary_for_label(opportunity: str, *, channel_label: str) -> str:
    return _bounded_text(
        f"Kortny may be able to help in {channel_label}: {opportunity}",
        1000,
    )


def _suggested_action(opportunity: str) -> str:
    return _bounded_text(f"Offer help with: {opportunity}", 500)


def _suggested_message(
    opportunity: str,
    *,
    membership: SlackChannelMembership,
) -> str:
    channel = f"#{membership.channel_name}" if membership.channel_name else "this channel"
    return _suggested_message_for_label(opportunity, channel_label=channel)


def _suggested_message_for_label(opportunity: str, *, channel_label: str) -> str:
    return _bounded_text(
        f"I noticed {channel_label} may benefit from help with {opportunity}. "
        "Want me to take a pass?",
        500,
    )


def _task_response_opportunities(response_text: str) -> tuple[str, ...]:
    active = False
    output: list[str] = []
    seen: set[str] = set()
    for raw_line in response_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet_match = _BULLET_RE.match(line)
        if _is_watch_heading(line):
            active = True
            continue
        if active and bullet_match is None and output:
            break
        if not active or bullet_match is None:
            continue
        opportunity = _clean_task_opportunity(bullet_match.group(1))
        key = opportunity.lower()
        if not opportunity or key in seen:
            continue
        seen.add(key)
        output.append(opportunity)
        if len(output) >= MAX_TASK_RESPONSE_OPPORTUNITIES:
            break
    return tuple(output)


def _is_watch_heading(line: str) -> bool:
    heading = _normalize_for_key(line.strip("*_:"))
    return any(
        phrase in heading
        for phrase in (
            "what i watch for",
            "what i'll watch for",
            "what i should watch",
            "what should i watch",
            "what to watch for",
            "watch for here",
            "watching for",
        )
    )


def _clean_task_opportunity(value: str) -> str:
    text = (
        value.replace("\u00a0", " ")
        .replace("\u2011", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    text = re.sub(r"^\*([^*]{1,80})\*\s*[-:]\s*", r"\1: ", text)
    text = re.sub(r"^([^:]{1,80})\s+-\s+", r"\1: ", text)
    text = text.strip("* ")
    return _bounded_text(text, 220)


def _task_response_evidence(
    *,
    task: Task,
    opportunity: str,
    response_text: str,
    channel_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "type": "task_response",
            "source_task_id": str(task.id),
            "channel_id": channel_id,
            "snippet": _bounded_text(opportunity, 300),
        },
        {
            "type": "task_response_context",
            "source_task_id": str(task.id),
            "channel_id": channel_id,
            "summary": _bounded_text(response_text, 700),
        },
    ]


def _bounded_text_list(value: object, *, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = _bounded_text(item, 220)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return tuple(output)


def _bounded_text(value: str, max_chars: int) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()[:max_chars].strip()
