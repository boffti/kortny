"""Egress safety for outbound Slack posts (HIG-169 P0.1).

Link unfurling is the exact vector that exfiltrated data from Slack AI and
Anthropic's own Slack MCP server: an attacker plants a markdown link whose URL
carries stolen context in its query string, and Slack's unfurl preview fetches
it (or the victim hovers it) — no click required. The real fix is turning
unfurling off at the posting boundary (see ``SlackPoster``). This module is the
observability half: it scans outbound text for URLs whose query string looks
like it is carrying a payload to a non-allowlisted host, so an operator can see
attempted exfiltration even though we do not block by default (annoyance
budget). Flag + log only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# Bare URLs and Slack-mrkdwn <url|label> / <url> links.
_URL_RE = re.compile(r"https?://[^\s<>|]+", re.IGNORECASE)

# A query string "looks like a payload" when any value is long or high-entropy
# enough to plausibly carry exfiltrated context rather than a normal param.
_SUSPICIOUS_VALUE_MIN_LEN = 64


@dataclass(frozen=True, slots=True)
class FlaggedEgressUrl:
    """One outbound URL whose query string looks like an exfiltration payload."""

    url: str
    host: str
    longest_value_len: int


def parse_egress_allowlist(raw: str | None) -> frozenset[str]:
    """Parse a CSV of bare hostnames into a normalized, lowercased set."""

    if not raw:
        return frozenset()
    hosts = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(hosts)


def scan_outbound_urls(
    text: str,
    *,
    allowlist: frozenset[str] = frozenset(),
) -> tuple[FlaggedEgressUrl, ...]:
    """Return URLs to a non-allowlisted host carrying a suspicious query payload.

    Deterministic and conservative: only URLs that both (a) point at a host not
    in ``allowlist`` and (b) carry a query value at least
    ``_SUSPICIOUS_VALUE_MIN_LEN`` chars long are returned. A URL with no query
    string, or only short params, is never flagged — most legitimate links pass.
    """

    if not text:
        return ()
    flagged: list[FlaggedEgressUrl] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;)]>\"'")
        if url in seen:
            continue
        seen.add(url)
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host or host in allowlist:
            continue
        if not parts.query:
            continue
        longest = _longest_query_value_len(parts.query)
        if longest < _SUSPICIOUS_VALUE_MIN_LEN:
            continue
        flagged.append(FlaggedEgressUrl(url=url, host=host, longest_value_len=longest))
    return tuple(flagged)


def _longest_query_value_len(query: str) -> int:
    longest = 0
    for pair in query.split("&"):
        _, _, value = pair.partition("=")
        # urlencoded payloads inflate length; the raw length is a fine signal.
        longest = max(longest, len(value))
    return longest


__all__ = [
    "FlaggedEgressUrl",
    "parse_egress_allowlist",
    "scan_outbound_urls",
]
