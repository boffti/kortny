# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Lint, format, typecheck, test (all checks)
make check

# Individual checks
make lint          # ruff check
make lint-fix      # ruff check --fix
make format        # ruff format
make typecheck     # mypy
make test          # pytest

# Single test
uv run pytest tests/path/to/test_file.py::test_name

# DB-backed tests require a separate test database (never run against dev DB)
KORTNY_TEST_POSTGRES_URL=postgresql://kortny:kortny@localhost:5432/kortny_test uv run pytest

# Database migrations
make migrate       # alembic upgrade head
make downgrade     # alembic downgrade base

# Run services (Docker Compose)
make compose-up                    # postgres + app + worker + dashboard
make compose-up-observability      # + Phoenix OTEL tracing
make compose-logs-workflow         # app + worker + temporal + temporal-worker logs

# ADK playground (for adk_spike)
make playground    # uv run adk web .
```

## Architecture

Kortny is a Slack-native AI coworker. Slack events create durable tasks that a background worker executes via an LLM + tool loop.

### Request flow

1. **`kortny/slack/`** — Slack Bolt app (`kortny.slack.__main__`). `SlackIngress` converts incoming Slack events (app mentions, DMs, channel messages, reactions) into `Task` rows via `TaskService`. Intent classifier (`kortny/intent/`) decides whether a soft channel mention warrants a task.

2. **`kortny/queue/`** — Postgres queue using `SELECT ... FOR UPDATE SKIP LOCKED`. Workers poll for `queued` tasks.

3. **`kortny/worker/`** — Background worker (`kortny.worker.__main__`). `AgentExecutor` picks up tasks and runs `AgentCoordinator`.

4. **`kortny/agent/coordinator.py`** — Core LLM loop. Calls LiteLLM via `LLMService`, dispatches tool calls from `ToolRegistry`, records every turn as `TaskEvent` rows, enforces execution guardrails (max turns, max tool calls, circuit breaker for repeated failures). Has two execution modes: inline (default) and planned (LLM generates an explicit plan before executing).

5. **`kortny/workflow/`** — Temporal integration (optional). `KORTNY_WORKFLOW_BACKEND=temporal` routes tasks through `kortny.workflow.__main__` instead of the inline worker. `planning_classifier.py` decides which tasks need planned parallel workflows.

6. **Results** — `SlackPoster` posts the final `result_summary` back to the originating Slack thread.

### Key modules

| Module | Purpose |
|--------|---------|
| `kortny/db/models.py` | SQLAlchemy ORM: `Task`, `TaskEvent`, `Installation`, `WorkspaceState`, `Episode`, and more |
| `kortny/tools/` | Tool registry + built-in tools (web search, PDF, Slack channel history, file read, Composio executor) |
| `kortny/llm/` | LiteLLM wrapper + routing; `LLMService` records usage to DB |
| `kortny/memory/` | Workspace state (key/value facts) + episodic memory |
| `kortny/composio/` | Composio integration provider; `composio_execute` tool bridges Composio actions |
| `kortny/dashboard/` | FastAPI read-only observability dashboard (port 8080) |
| `kortny/observability/` | OpenTelemetry tracing; Phoenix (Arize) used as local OTEL backend |
| `kortny/observe/` | Ambient channel observation + profile assessment (passive, no task created) |
| `kortny/intent/` | LLM-backed intent classifier for soft channel mentions |
| `kortny/agent/context.py` | Assembles system prompt + thread history + workspace memory into messages |
| `kortny/agent/execution.py` | Guardrail limits, execution plan, budget tracking |
| `kortny/knowledge_graph/` | Workspace knowledge graph (entity/relation provenance, scoped graph queries) |
| `kortny/skills/` | Reusable agent skill definitions; `builtins.py` registers default skills |
| `kortny/approvals.py` | Tool approval gate — certain tools require explicit user confirmation before execution |

### Services in compose.yaml

- `postgres` — primary store (tasks, events, memory, all state)
- `app` — Slack Bolt event handler (`kortny.slack`)
- `worker` — task executor (`kortny.worker`)
- `dashboard` — FastAPI observability UI (`kortny.dashboard.app`)
- `temporal` — optional durable workflow engine
- `temporal-worker` — Temporal worker (`kortny.workflow`)
- `phoenix` — optional OTEL/tracing UI (profile: `observability`)

### Database

Migrations live in `kortny/db/migrations/versions/`. Always create new migrations with Alembic; never edit applied ones. Schema source of truth: `docs/schema.dbml`.

### Environment variables

Copy `.env.example` to `.env`. Key variables:
- `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` — required for Slack
- `POSTGRES_URL` — defaults to `postgresql://kortny:kortny@localhost:5432/kortny`
- `KORTNY_WORKFLOW_BACKEND` — `inline` (default) or `temporal`
- `AGENT_RUNTIME` — `adk` (default) selects Google ADK runtime; other values use legacy coordinator
- `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` — primary LLM config; model tiers (`LLM_CHEAP_MODEL`, `LLM_STANDARD_MODEL`, `LLM_ANALYSIS_MODEL`, `LLM_DOCUMENT_MODEL`, `LLM_HIGH_REASONING_MODEL`) override per task type
- `OBSERVABILITY_ENABLED` / `OTEL_EXPORTER_OTLP_ENDPOINT` — tracing config; set endpoint to Phoenix (`http://phoenix:6006/v1/traces`) or Langfuse Cloud
- `BRAVE_SEARCH_API_KEY` — required for web search tool
- `COMPOSIO_API_KEY` — required for Composio integrations

### Testing

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Tests live in `tests/`. The test database should be real Postgres, not mocked — integration tests rely on actual query behavior.

### Tool authoring

New tools implement the interface in `kortny/tools/types.py` and register in `kortny/tools/registry.py`. Return `ToolResult`; raise `RecoverableToolError` for errors the coordinator should retry or route around.
