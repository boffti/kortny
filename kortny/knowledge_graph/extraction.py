"""Low-risk extraction paths into the workspace knowledge graph."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    KnowledgeGraphEdge,
    KnowledgeGraphEntity,
    ObserveChannelProfile,
    SlackChannelMembership,
    Task,
)
from kortny.knowledge_graph.scopes import VisibilityScope
from kortny.knowledge_graph.service import EvidenceInput, GraphService

CHANNEL_ENTITY_TYPE = "channel"
CHANNEL_PROFILE_ENTITY_TYPE = "firm_fact"
CHANNEL_PROFILE_RELATIONSHIP = "relates_to"
KG_CHANNEL_PROFILE_PROJECTED_MESSAGE = "kg_channel_profile_projected"
SEMANTIC_PROJECTION_KIND = "channel_semantic_projection"
SEMANTIC_PROJECTION_PREFIXES = (
    "channel_topic",
    "channel_workflow",
    "channel_entity",
    "channel_assumption",
    "channel_help",
)
SEMANTIC_ENTITY_SPECS = (
    ("recurring_topics", "channel_topic", "firm_fact", "topic"),
    ("workflows", "channel_workflow", "commitment", "workflow"),
    ("important_entities", "channel_entity", "external_entity", "important_entity"),
    ("assumptions", "channel_assumption", "firm_fact", "assumption"),
    ("help_opportunities", "channel_help", "firm_fact", "help_opportunity"),
)


@dataclass(frozen=True)
class KnowledgeGraphProjectionResult:
    channel_entity_id: str
    profile_entity_id: str | None
    profile_edge_id: str | None
    entity_count: int
    edge_count: int
    evidence_count: int


class KnowledgeGraphExtractionService:
    """Project already-approved system observations into graph rows.

    This service deliberately avoids broad LLM extraction. It only records
    authoritative channel existence and stores channel assessment summaries as
    channel-scoped candidates for later review.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.graph = GraphService(session)

    def project_channel_profile(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
        profile: ObserveChannelProfile,
    ) -> KnowledgeGraphProjectionResult:
        """Project a completed Observe channel profile into KG candidates."""

        entity_count = 0
        edge_count = 0
        evidence_count = 0
        channel_entity, created_channel = self._upsert_channel_entity(
            task=task,
            membership=membership,
        )
        entity_count += int(created_channel)
        evidence_count += 1

        profile_entity, profile_created = self._replace_channel_profile_entity(
            task=task,
            membership=membership,
            profile=profile,
        )
        entity_count += int(profile_created)
        evidence_count += 1

        self._supersede_current_profile_edges(channel_entity)
        profile_edge = self.graph.create_edge(
            installation_id=task.installation_id,
            source_entity_id=channel_entity.id,
            target_entity_id=profile_entity.id,
            relationship_type=CHANNEL_PROFILE_RELATIONSHIP,
            visibility_scope=_scope_for_membership(membership),
            source_type="onboarding_scan",
            lifecycle_state="candidate",
            confidence_score=profile.confidence_score or Decimal("0.500"),
            confidence_reason=profile.confidence_reason,
            freshness_window_days=profile.fresh_window_days,
            attrs_json={
                "kind": "channel_profile_projection",
                "profile_id": str(profile.id),
                "profile_version": profile.profile_version,
            },
            evidence=_profile_evidence(task, membership, profile),
        )
        edge_count += 1
        evidence_count += 1

        self._supersede_current_semantic_projection(
            task=task,
            membership=membership,
        )
        semantic_entity_count, semantic_edge_count, semantic_evidence_count = (
            self._project_semantic_extraction(
                task=task,
                membership=membership,
                profile=profile,
                channel_entity=channel_entity,
                profile_entity=profile_entity,
            )
        )
        entity_count += semantic_entity_count
        edge_count += semantic_edge_count
        evidence_count += semantic_evidence_count

        self.session.flush()
        return KnowledgeGraphProjectionResult(
            channel_entity_id=str(channel_entity.id),
            profile_entity_id=str(profile_entity.id),
            profile_edge_id=str(profile_edge.id),
            entity_count=entity_count,
            edge_count=edge_count,
            evidence_count=evidence_count,
        )

    def _upsert_channel_entity(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
    ) -> tuple[KnowledgeGraphEntity, bool]:
        canonical_key = _channel_canonical_key(membership.channel_id)
        existing = self._current_entity_by_key(task.installation_id, canonical_key)
        attrs = {
            "channel_id": membership.channel_id,
            "channel_name": membership.channel_name,
            "channel_type": membership.channel_type,
            "membership_status": membership.membership_status,
            "discovered_via": membership.discovered_via,
            "membership_id": str(membership.id),
        }
        if existing is not None:
            existing.display_name = _channel_display_name(membership)
            existing.attrs_json = attrs
            existing.visibility_scope_type = _scope_for_membership(
                membership
            ).scope_type
            existing.visibility_scope_id = _scope_for_membership(membership).scope_id
            existing.source_type = "slack_authoritative"
            existing.lifecycle_state = "active"
            existing.is_current = True
            self.graph.add_evidence(
                installation_id=task.installation_id,
                target_kind="entity",
                target_id=existing.id,
                evidence=_channel_evidence(task, membership),
            )
            self.session.flush()
            return existing, False

        entity = self.graph.create_entity(
            installation_id=task.installation_id,
            entity_type=CHANNEL_ENTITY_TYPE,
            canonical_key=canonical_key,
            display_name=_channel_display_name(membership),
            external_ref_type="slack_channel",
            external_ref_id=membership.channel_id,
            attrs_json=attrs,
            visibility_scope=_scope_for_membership(membership),
            source_type="slack_authoritative",
            lifecycle_state="active",
            confidence_score=Decimal("1.000"),
            confidence_reason="Slack channel membership is authoritative.",
            evidence=_channel_evidence(task, membership),
        )
        return entity, True

    def _replace_channel_profile_entity(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
        profile: ObserveChannelProfile,
    ) -> tuple[KnowledgeGraphEntity, bool]:
        canonical_key = _profile_canonical_key(membership.channel_id)
        existing = self._current_entity_by_key(task.installation_id, canonical_key)
        if existing is not None:
            self.graph.supersede_entity(existing)
            self.session.flush()

        entity = self.graph.create_entity(
            installation_id=task.installation_id,
            entity_type=CHANNEL_PROFILE_ENTITY_TYPE,
            canonical_key=canonical_key,
            display_name=f"Channel profile for {_channel_display_name(membership)}",
            external_ref_type="observe_channel_profile",
            external_ref_id=str(profile.id),
            attrs_json={
                "kind": "observe_channel_profile",
                "profile_id": str(profile.id),
                "profile_version": profile.profile_version,
                "summary": profile.summary,
                "profile": profile.profile_json,
                "assumptions": profile.assumptions_json,
                "evidence_refs": profile.evidence_refs_json,
                "message_count": profile.message_count,
                "file_count": profile.file_count,
                "fresh_window_days": profile.fresh_window_days,
            },
            visibility_scope=_scope_for_membership(membership),
            source_type="onboarding_scan",
            lifecycle_state="candidate",
            confidence_score=profile.confidence_score or Decimal("0.500"),
            confidence_reason=profile.confidence_reason,
            freshness_window_days=profile.fresh_window_days,
            evidence=_profile_evidence(task, membership, profile),
        )
        return entity, True

    def _supersede_current_profile_edges(
        self,
        channel_entity: KnowledgeGraphEntity,
    ) -> None:
        edges = self.session.scalars(
            select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.installation_id == channel_entity.installation_id,
                KnowledgeGraphEdge.source_entity_id == channel_entity.id,
                KnowledgeGraphEdge.relationship_type == CHANNEL_PROFILE_RELATIONSHIP,
                KnowledgeGraphEdge.source_type == "onboarding_scan",
                KnowledgeGraphEdge.is_current.is_(True),
                KnowledgeGraphEdge.expired_at.is_(None),
            )
        )
        for edge in edges:
            self.graph.supersede_edge(edge)
        self.session.flush()

    def _supersede_current_semantic_projection(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
    ) -> None:
        prefix_filters = [
            KnowledgeGraphEntity.canonical_key.like(
                f"{prefix}:{membership.channel_id}:%"
            )
            for prefix in SEMANTIC_PROJECTION_PREFIXES
        ]
        entities = list(
            self.session.scalars(
                select(KnowledgeGraphEntity).where(
                    KnowledgeGraphEntity.installation_id == task.installation_id,
                    KnowledgeGraphEntity.is_current.is_(True),
                    KnowledgeGraphEntity.expired_at.is_(None),
                    KnowledgeGraphEntity.source_type == "onboarding_scan",
                    or_(*prefix_filters),
                )
            )
        )
        entity_ids = [entity.id for entity in entities]
        if entity_ids:
            edges = self.session.scalars(
                select(KnowledgeGraphEdge).where(
                    KnowledgeGraphEdge.installation_id == task.installation_id,
                    KnowledgeGraphEdge.is_current.is_(True),
                    KnowledgeGraphEdge.expired_at.is_(None),
                    or_(
                        KnowledgeGraphEdge.source_entity_id.in_(entity_ids),
                        KnowledgeGraphEdge.target_entity_id.in_(entity_ids),
                    ),
                )
            )
            for edge in edges:
                self.graph.supersede_edge(edge)
        for entity in entities:
            self.graph.supersede_entity(entity)
        self.session.flush()

    def _project_semantic_extraction(
        self,
        *,
        task: Task,
        membership: SlackChannelMembership,
        profile: ObserveChannelProfile,
        channel_entity: KnowledgeGraphEntity,
        profile_entity: KnowledgeGraphEntity,
    ) -> tuple[int, int, int]:
        extraction = _semantic_extraction(profile)
        if extraction is None:
            return 0, 0, 0

        entity_count = 0
        edge_count = 0
        evidence_count = 0
        scope = _scope_for_membership(membership)
        confidence_score = _semantic_confidence_score(
            extraction.get("confidence"),
            profile.confidence_score,
        )

        for field_name, key_prefix, entity_type, semantic_kind in SEMANTIC_ENTITY_SPECS:
            values = _semantic_values(extraction.get(field_name))
            for value in values:
                canonical_key = _semantic_canonical_key(
                    key_prefix=key_prefix,
                    channel_id=membership.channel_id,
                    label=value,
                )
                semantic_entity = self.graph.create_entity(
                    installation_id=task.installation_id,
                    entity_type=entity_type,
                    canonical_key=canonical_key,
                    display_name=value,
                    attrs_json={
                        "kind": SEMANTIC_PROJECTION_KIND,
                        "semantic_kind": semantic_kind,
                        "source_field": field_name,
                        "profile_id": str(profile.id),
                        "profile_version": profile.profile_version,
                        "channel_id": membership.channel_id,
                        "confidence": extraction.get("confidence"),
                        "evidence": _semantic_values(extraction.get("evidence")),
                    },
                    visibility_scope=scope,
                    source_type="onboarding_scan",
                    lifecycle_state="candidate",
                    confidence_score=confidence_score,
                    confidence_reason=_semantic_confidence_reason(profile),
                    freshness_window_days=profile.fresh_window_days,
                    evidence=_semantic_evidence(
                        task=task,
                        membership=membership,
                        profile=profile,
                        value=value,
                        semantic_kind=semantic_kind,
                    ),
                )
                entity_count += 1
                evidence_count += 1

                channel_edge = self.graph.create_edge(
                    installation_id=task.installation_id,
                    source_entity_id=channel_entity.id,
                    target_entity_id=semantic_entity.id,
                    relationship_type="relates_to",
                    visibility_scope=scope,
                    source_type="onboarding_scan",
                    lifecycle_state="candidate",
                    confidence_score=confidence_score,
                    confidence_reason=_semantic_confidence_reason(profile),
                    freshness_window_days=profile.fresh_window_days,
                    attrs_json={
                        "kind": SEMANTIC_PROJECTION_KIND,
                        "semantic_kind": semantic_kind,
                        "source_field": field_name,
                        "profile_id": str(profile.id),
                    },
                    evidence=_semantic_evidence(
                        task=task,
                        membership=membership,
                        profile=profile,
                        value=value,
                        semantic_kind=semantic_kind,
                    ),
                )
                profile_edge = self.graph.create_edge(
                    installation_id=task.installation_id,
                    source_entity_id=profile_entity.id,
                    target_entity_id=semantic_entity.id,
                    relationship_type="maps_to",
                    visibility_scope=scope,
                    source_type="onboarding_scan",
                    lifecycle_state="candidate",
                    confidence_score=confidence_score,
                    confidence_reason=_semantic_confidence_reason(profile),
                    freshness_window_days=profile.fresh_window_days,
                    attrs_json={
                        "kind": SEMANTIC_PROJECTION_KIND,
                        "semantic_kind": semantic_kind,
                        "source_field": field_name,
                        "profile_id": str(profile.id),
                    },
                    evidence=_semantic_evidence(
                        task=task,
                        membership=membership,
                        profile=profile,
                        value=value,
                        semantic_kind=semantic_kind,
                    ),
                )
                edge_count += int(channel_edge is not None) + int(profile_edge is not None)
                evidence_count += 2

        return entity_count, edge_count, evidence_count

    def _current_entity_by_key(
        self,
        installation_id: object,
        canonical_key: str,
    ) -> KnowledgeGraphEntity | None:
        return self.session.scalar(
            select(KnowledgeGraphEntity).where(
                KnowledgeGraphEntity.installation_id == installation_id,
                KnowledgeGraphEntity.canonical_key == canonical_key,
                KnowledgeGraphEntity.is_current.is_(True),
                KnowledgeGraphEntity.expired_at.is_(None),
            )
        )


def _channel_canonical_key(channel_id: str) -> str:
    return f"slack_channel:{channel_id}"


def _profile_canonical_key(channel_id: str) -> str:
    return f"channel_profile:{channel_id}"


def _channel_display_name(membership: SlackChannelMembership) -> str:
    return (
        f"#{membership.channel_name}"
        if membership.channel_name
        else membership.channel_id
    )


def _scope_for_membership(membership: SlackChannelMembership) -> VisibilityScope:
    channel_type = (membership.channel_type or "").lower()
    if channel_type in {"group", "private_channel"} or membership.channel_id.startswith(
        "G"
    ):
        return VisibilityScope.private_channel(membership.channel_id)
    return VisibilityScope.channel(membership.channel_id)


def _channel_evidence(
    task: Task,
    membership: SlackChannelMembership,
) -> EvidenceInput:
    return EvidenceInput(
        source_type="slack_authoritative",
        extracted_by="slack_channel_membership",
        source_task_id=task.id,
        source_slack_channel_id=membership.channel_id,
        source_slack_message_ts=membership.onboarding_message_ts,
        raw_snippet=f"Kortny is active in Slack channel {membership.channel_id}.",
        confidence_score=Decimal("1.000"),
        confidence_reason="Slack channel membership row.",
    )


def _profile_evidence(
    task: Task,
    membership: SlackChannelMembership,
    profile: ObserveChannelProfile,
) -> EvidenceInput:
    return EvidenceInput(
        source_type="onboarding_scan",
        extracted_by="observe_channel_profile",
        source_task_id=task.id,
        source_slack_channel_id=membership.channel_id,
        source_slack_message_ts=task.slack_message_ts,
        raw_snippet=(profile.summary or "")[:1000],
        confidence_score=profile.confidence_score,
        confidence_reason=profile.confidence_reason,
    )


def _semantic_extraction(profile: ObserveChannelProfile) -> dict[str, Any] | None:
    candidates = (
        profile.profile_json.get("semantic_extraction")
        if isinstance(profile.profile_json, dict)
        else None
    )
    if not isinstance(candidates, dict):
        candidates = (
            profile.metadata_json.get("semantic_extraction")
            if isinstance(profile.metadata_json, dict)
            else None
        )
    if not isinstance(candidates, dict):
        return None
    if not any(_semantic_values(candidates.get(field)) for field, *_ in SEMANTIC_ENTITY_SPECS):
        return None
    return candidates


def _semantic_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = _bounded_semantic_text(item)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= 5:
            break
    return tuple(output)


def _bounded_semantic_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:180].strip()


def _semantic_canonical_key(
    *,
    key_prefix: str,
    channel_id: str,
    label: str,
) -> str:
    return f"{key_prefix}:{channel_id}:{_slugify(label)}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:72].strip("-") or "unknown"


def _semantic_confidence_score(
    confidence: object,
    fallback: Decimal | None,
) -> Decimal:
    if confidence == "high":
        return Decimal("0.700")
    if confidence == "medium":
        return Decimal("0.600")
    if confidence == "low":
        return Decimal("0.400")
    return fallback or Decimal("0.500")


def _semantic_confidence_reason(profile: ObserveChannelProfile) -> str:
    return (
        "Candidate extracted from bounded channel assessment; requires review "
        f"before runtime use. Profile version {profile.profile_version}."
    )


def _semantic_evidence(
    *,
    task: Task,
    membership: SlackChannelMembership,
    profile: ObserveChannelProfile,
    value: str,
    semantic_kind: str,
) -> EvidenceInput:
    return EvidenceInput(
        source_type="onboarding_scan",
        extracted_by="channel_semantic_projection",
        source_task_id=task.id,
        source_slack_channel_id=membership.channel_id,
        source_slack_message_ts=task.slack_message_ts,
        raw_snippet=f"{semantic_kind}: {value}",
        confidence_score=_semantic_confidence_score(
            (profile.profile_json or {}).get("semantic_extraction", {}).get(
                "confidence"
            )
            if isinstance(profile.profile_json, dict)
            else None,
            profile.confidence_score,
        ),
        confidence_reason=_semantic_confidence_reason(profile),
    )
