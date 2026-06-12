# Provenance

**Concept source**: michalparkola/tapestry-skills (youtube-transcript skill)
**Source repo**: https://github.com/michalparkola/tapestry-skills
**License**: MIT
**Commit reference**: HEAD as of 2026-06-12 (concept-level reference; no code copied)
**Adaptation date**: 2026-06-12
**Adapted by**: Agent A (HIG-239)

## What was adapted

The SKILL.md is an original clean-room authorship inspired by the tapestry-skills youtube-transcript concept. The transcript script (`scripts/get_transcript.py`) is an original implementation using `yt-dlp` — no code was copied from the upstream source.

## Key adaptations from upstream

- **Whisper fallback stripped entirely** per plan instruction: this skill uses only subtitle tracks retrieved by yt-dlp — no audio download, no audio transcription.
- Output modes expanded: full transcript, summary, structured notes, action items.
- Quality flag added: auto-generated captions are noted in the output metadata.
- VTT parsing is custom (strips timing lines, deduplicates repeated captions in auto-generated tracks).
- Private/geo-restricted video error handling made explicit.
- Slack file upload is the default delivery for long transcripts.

## License

MIT License — michalparkola/tapestry-skills (concept reference only; no copied text or code).

The original MIT license text is reproduced below for compliance.
