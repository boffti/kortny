# Provenance

Independently authored for Kortny (2026-06-12). Concept and capability slot informed by research into https://github.com/TerminalSkills/skills (Apache-2.0); no upstream text or files were copied.

## Design notes

- No subprocess git-log requirement; input is provided directly by the user.
- Output targets Slack post + canvas/file for longer changelogs rather than local files.
- Changelog format reference provided as `references/changelog-format.md` (format spec follows keepachangelog.com, which is CC0/public domain).
- No scripts — pure text transformation handled by the LLM.
