# Provenance

**Concept source**: michalparkola/tapestry-skills (article-extractor skill)
**Source repo**: https://github.com/michalparkola/tapestry-skills
**License**: MIT
**Commit reference**: HEAD as of 2026-06-12 (concept-level reference; no code copied)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent A (HIG-239)

## What was adapted

The SKILL.md is an original clean-room authorship inspired by the tapestry-skills article-extractor concept. The extraction script (`scripts/extract_article.py`) is an original implementation using `trafilatura` — no code was copied from the upstream source.

## Key adaptations from upstream

- **Whisper fallback stripped entirely** per plan instruction: this skill uses subtitle tracks only via `trafilatura`; no audio-based transcription.
- Output delivery adapted for Slack (file upload for long articles, inline for short briefs).
- No IDE or `.claude/` path assumptions.
- Script outputs JSON (title/author/date/url/text/word_count) rather than raw text, enabling structured post-processing by the coordinator.
- Quality flags added: paywall detection, JS-heavy page detection via low word count.

## License

MIT License — michalparkola/tapestry-skills (concept reference only; no copied text or code).

The original MIT license text is reproduced below for compliance.
