## What does this PR do?

<!-- One or two sentences. Link the issue it closes, e.g. "Closes #123". -->

## How was it tested?

<!-- Commands run, tests added, manual verification steps. -->

## Checklist

- [ ] `make check` passes (ruff lint + format, mypy, pytest)
- [ ] Tests added or updated for behavior changes
- [ ] New tools have both a `ToolMetadata` catalog entry and a factory registration
- [ ] DB changes are a new Alembic migration (never an edit to an applied one)
- [ ] Commits are signed off (`git commit -s`, see CONTRIBUTING.md)
- [ ] No secrets, tokens, or real workspace data in code, tests, or fixtures
