from kortny.db.models import Base, LLMProvider, TaskEventType, TaskStatus


def test_mvp_schema_declares_all_core_tables() -> None:
    assert set(Base.metadata.tables) == {
        "installations",
        "encrypted_secrets",
        "tasks",
        "task_events",
        "llm_usage",
        "artifacts",
        "model_pricing",
    }


def test_task_status_enum_matches_locked_schema() -> None:
    assert [status.value for status in TaskStatus] == [
        "pending",
        "running",
        "succeeded",
        "failed",
        "crashed",
        "cancelled",
    ]


def test_llm_provider_enum_matches_locked_schema() -> None:
    assert [provider.value for provider in LLMProvider] == [
        "openai",
        "anthropic",
        "openrouter",
    ]


def test_task_event_type_enum_matches_locked_schema() -> None:
    assert [event_type.value for event_type in TaskEventType] == [
        "task_created",
        "status_changed",
        "llm_call",
        "tool_call",
        "tool_result",
        "artifact_created",
        "message_posted",
        "error",
        "log",
    ]


def test_task_table_has_queue_and_thread_indexes() -> None:
    task_table = Base.metadata.tables["tasks"]
    index_names = {index.name for index in task_table.indexes}

    assert {"idx_tasks_claim", "idx_tasks_history", "idx_tasks_thread"} <= index_names
