# Provenance

Independently authored for Kortny (2026-06-12). Concept and capability slot informed by research into https://github.com/phuryn/pm-skills (MIT) and https://github.com/TerminalSkills/skills (Apache 2.0); no upstream text or files were copied.

## Design notes

The PM-workflow orientation — structured decision log, action items with owners/due dates, blocker tracking — was chosen to provide genuine differentiation from the existing `meeting-notes-summarizer` skill. A more general-purpose meeting-notes approach would have duplicated that skill without adding value.

- Explicit differentiation section vs. `meeting-notes-summarizer` included in SKILL.md.
- Composio PM tool integration added (Jira, Linear, Notion, Asana action item push).
- Output targets Slack post + PM tool sync rather than local file output.
- Next-meeting agenda seed feature added.
- Meeting artifact template provided as `references/meeting-artifact-template.md`.
