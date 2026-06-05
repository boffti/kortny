"""Witness candidate primitives for proactive Kortny behavior."""

from kortny.witness.extractor import (
    WITNESS_CHANNEL_PROFILE_EXTRACTOR_PROMPT_NAME,
    WITNESS_CHANNEL_PROFILE_EXTRACTOR_RESPONSE_FORMAT,
    WITNESS_TASK_RESPONSE_EXTRACTOR_PROMPT_NAME,
    WITNESS_TASK_RESPONSE_EXTRACTOR_RESPONSE_FORMAT,
    WitnessChannelProfileExtractor,
    WitnessTaskResponseExtraction,
    WitnessTaskResponseExtractor,
    parse_witness_channel_profile_extraction,
    parse_witness_task_response_extraction,
)
from kortny.witness.opportunities import (
    ALLOWED_CANDIDATE_TYPES,
    WITNESS_OPPORTUNITY_CANDIDATES_PROJECTED_MESSAGE,
    WitnessOpportunityCandidateInput,
    WitnessOpportunityCandidateResult,
    WitnessOpportunityService,
)

__all__ = [
    "ALLOWED_CANDIDATE_TYPES",
    "WITNESS_CHANNEL_PROFILE_EXTRACTOR_PROMPT_NAME",
    "WITNESS_CHANNEL_PROFILE_EXTRACTOR_RESPONSE_FORMAT",
    "WITNESS_TASK_RESPONSE_EXTRACTOR_PROMPT_NAME",
    "WITNESS_TASK_RESPONSE_EXTRACTOR_RESPONSE_FORMAT",
    "WITNESS_OPPORTUNITY_CANDIDATES_PROJECTED_MESSAGE",
    "WitnessOpportunityCandidateInput",
    "WitnessOpportunityCandidateResult",
    "WitnessOpportunityService",
    "WitnessChannelProfileExtractor",
    "WitnessTaskResponseExtraction",
    "WitnessTaskResponseExtractor",
    "parse_witness_channel_profile_extraction",
    "parse_witness_task_response_extraction",
]
