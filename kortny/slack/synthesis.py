"""Typed evidence contract for Slack response synthesis."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from kortny.tools.types import JsonObject

SYNTHESIS_CONTEXT_SCHEMA_VERSION = "2026-05-31.v1"


class SynthesisOutcome(StrEnum):
    """User-facing outcome state the synthesizer must honor."""

    ok = "ok"
    no_result = "no_result"
    partial_failure = "partial_failure"
    needs_approval = "needs_approval"
    error = "error"


class EvidenceKind(StrEnum):
    """Kind of evidence available to the response synthesizer."""

    tool_result = "tool_result"
    memory = "memory"
    artifact = "artifact"
    approval = "approval"
    error = "error"


class EvidenceTrust(StrEnum):
    """Trust boundary for evidence content."""

    trusted = "trusted"
    untrusted = "untrusted"


class SlackRef(BaseModel):
    """Typed Slack reference metadata for mention/channel validation."""

    channel_id: str | None = None
    thread_ts: str | None = None
    message_ts: str | None = None
    user_id: str | None = None
    file_id: str | None = None


class SynthesisEvidence(BaseModel):
    """Sanitized evidence item the synthesizer may rely on."""

    source_id: str
    kind: EvidenceKind
    content: str
    trust: EvidenceTrust = EvidenceTrust.untrusted
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tool: str | None = None
    urls: list[str] = Field(default_factory=list)
    slack_ref: SlackRef | None = None
    metadata: JsonObject = Field(default_factory=dict)


class SynthesisApprovalState(BaseModel):
    """Approval state visible to response synthesis."""

    tool: str | None = None
    status: str
    reason: str | None = None
    approver_user_id: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class SynthesisContext(BaseModel):
    """Typed boundary between agent execution and Slack final response."""

    schema_version: str = SYNTHESIS_CONTEXT_SCHEMA_VERSION
    user_intent: str
    outcome: SynthesisOutcome
    outcome_reason: str
    slack_surface: str
    threaded: bool
    addressee_user_id: str | None = None
    evidence: list[SynthesisEvidence] = Field(default_factory=list)
    approvals: list[SynthesisApprovalState] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    skills_loaded: list[str] = Field(default_factory=list)
    allowed_claim_sources: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)

    def to_payload(self) -> JsonObject:
        """Return a JSON-serializable payload for LLM and trace use."""

        return self.model_dump(mode="json")

    def summary_payload(self) -> JsonObject:
        """Return a compact trace payload for task events."""

        return {
            "synthesis_schema_version": self.schema_version,
            "synthesis_outcome": str(self.outcome),
            "synthesis_outcome_reason": self.outcome_reason,
            "synthesis_evidence_count": len(self.evidence),
            "synthesis_approval_count": len(self.approvals),
            "synthesis_uncertainty_count": len(self.uncertainty),
            "synthesis_skill_count": len(self.skills_loaded),
            "synthesis_evidence_kinds": [str(item.kind) for item in self.evidence],
            "synthesis_evidence_trust": [str(item.trust) for item in self.evidence],
            "synthesis_forbidden_claim_count": len(self.forbidden_claims),
        }
