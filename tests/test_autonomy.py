"""HIG-223 autonomy classifier matrix (pure, no DB)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from kortny.autonomy import (
    AutonomyLevel,
    AutonomyTier,
    classify_tool_risk,
    resolve_autonomy_level,
)
from kortny.tools.catalog import ToolMetadata, ToolSideEffect


def _meta(
    name: str = "external_tool",
    *,
    side_effect: ToolSideEffect = "write",
    capabilities: tuple[str, ...] = (),
) -> ToolMetadata:
    return ToolMetadata(
        name=name,
        namespace="external.tool",
        category="External",
        display_name=name,
        capabilities=capabilities,
        side_effect=side_effect,
    )


def _classify(sql: str, **kwargs: Any) -> AutonomyTier:
    args: Mapping[str, Any] = {"query": sql, **kwargs}
    return classify_tool_risk(_meta(side_effect="write"), args).tier


# --- SQL leading-verb parse --------------------------------------------------


def test_select_is_free() -> None:
    assert _classify("SELECT * FROM users") is AutonomyTier.implicit  # base write
    # A read query on a read tool stays free.
    assessment = classify_tool_risk(
        _meta(side_effect="read"), {"query": "SELECT * FROM users"}
    )
    assert assessment.tier is AutonomyTier.free


def test_explain_and_show_are_free_verbs() -> None:
    for verb_sql in ("EXPLAIN SELECT 1", "SHOW TABLES"):
        assessment = classify_tool_risk(_meta(side_effect="read"), {"query": verb_sql})
        assert assessment.tier is AutonomyTier.free


def test_insert_and_update_are_implicit() -> None:
    assert _classify("INSERT INTO t VALUES (1)") is AutonomyTier.implicit
    assert _classify("UPDATE t SET x = 1 WHERE id = 2") is AutonomyTier.implicit


def test_lowercase_and_leading_whitespace() -> None:
    assert _classify("   \n  delete from t where id = 1") is AutonomyTier.explicit
    assert _classify("\t\tupdate t set a=1") is AutonomyTier.implicit


def test_leading_comment_is_stripped() -> None:
    sql = "-- danger\n  DELETE FROM accounts WHERE id = 5"
    assert _classify(sql) is AutonomyTier.explicit
    block = "/* note */ INSERT INTO t VALUES (1)"
    assert _classify(block) is AutonomyTier.implicit


def test_delete_drop_truncate_alter_are_explicit() -> None:
    for sql in (
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE t",
        "ALTER TABLE t ADD COLUMN c int",
    ):
        assert _classify(sql) is AutonomyTier.explicit


def test_cte_with_delete_escalates_to_explicit() -> None:
    sql = "WITH doomed AS (SELECT id FROM t) DELETE FROM t WHERE id IN (SELECT id FROM doomed)"
    assert _classify(sql) is AutonomyTier.explicit


def test_cte_with_insert_is_implicit() -> None:
    sql = "WITH src AS (SELECT 1) INSERT INTO t SELECT * FROM src"
    assert _classify(sql) is AutonomyTier.implicit


def test_cte_with_only_select_is_free() -> None:
    sql = "WITH a AS (SELECT 1) SELECT * FROM a"
    assessment = classify_tool_risk(_meta(side_effect="read"), {"query": sql})
    assert assessment.tier is AutonomyTier.free


def test_ambiguous_cte_is_explicit() -> None:
    # A WITH with no recognised inner verb is treated conservatively.
    sql = "WITH x AS (foo bar baz)"
    assert _classify(sql) is AutonomyTier.explicit


# --- HTTP semantics ----------------------------------------------------------


def test_http_get_head_are_free() -> None:
    for method in ("GET", "HEAD"):
        assessment = classify_tool_risk(
            _meta(side_effect="read"), {"method": method, "url": "http://x"}
        )
        assert assessment.tier is AutonomyTier.free


def test_http_post_put_patch_are_implicit() -> None:
    for method in ("POST", "PUT", "PATCH"):
        assessment = classify_tool_risk(
            _meta(side_effect="write"), {"http_method": method}
        )
        assert assessment.tier is AutonomyTier.implicit


def test_http_delete_is_explicit() -> None:
    assessment = classify_tool_risk(
        _meta(side_effect="write"), {"method": "DELETE", "url": "http://x"}
    )
    assert assessment.tier is AutonomyTier.explicit


# --- Bulk escalation ---------------------------------------------------------


def test_list_of_ids_escalates_one_tier() -> None:
    # implicit base -> explicit when a list-of-ids arg is present.
    assessment = classify_tool_risk(
        _meta(side_effect="write"), {"record_ids": ["1", "2", "3"]}
    )
    assert assessment.tier is AutonomyTier.explicit
    assert any(r.startswith("bulk_") for r in assessment.reasons)


def test_literal_all_escalates() -> None:
    assessment = classify_tool_risk(_meta(side_effect="write"), {"target": "all"})
    assert assessment.tier is AutonomyTier.explicit


def test_wildcard_escalates() -> None:
    assessment = classify_tool_risk(_meta(side_effect="write"), {"pattern": "*"})
    assert assessment.tier is AutonomyTier.explicit


def test_bulk_does_not_escalate_free_reads() -> None:
    assessment = classify_tool_risk(_meta(side_effect="read"), {"ids": ["1", "2"]})
    assert assessment.tier is AutonomyTier.free


# --- Metadata + unknown conservatism ----------------------------------------


def test_destructive_metadata_is_always_explicit() -> None:
    assessment = classify_tool_risk(_meta(side_effect="destructive"), {})
    assert assessment.tier is AutonomyTier.explicit


def test_unknown_write_tool_is_implicit_not_free() -> None:
    assessment = classify_tool_risk(_meta(side_effect="write"), {})
    assert assessment.tier is AutonomyTier.implicit


def test_outward_capability_forces_explicit() -> None:
    assessment = classify_tool_risk(
        _meta(
            name="send_email",
            side_effect="write",
            capabilities=("email", "send"),
        ),
        {"to": "a@b.com"},
    )
    assert assessment.tier is AutonomyTier.explicit


def test_read_tool_with_write_capability_word_is_implicit() -> None:
    assessment = classify_tool_risk(
        _meta(name="t", side_effect="read", capabilities=("create_issue",)),
        {},
    )
    assert assessment.tier is AutonomyTier.implicit


# --- Level resolution --------------------------------------------------------


def test_resolution_channel_beats_workspace() -> None:
    level = resolve_autonomy_level(
        channel_level="autonomous", workspace_level="conservative"
    )
    assert level is AutonomyLevel.autonomous


def test_resolution_workspace_when_no_channel() -> None:
    level = resolve_autonomy_level(channel_level=None, workspace_level="conservative")
    assert level is AutonomyLevel.conservative


def test_resolution_default_when_missing() -> None:
    level = resolve_autonomy_level(channel_level=None, workspace_level=None)
    assert level is AutonomyLevel.balanced


def test_resolution_ignores_unknown_values() -> None:
    level = resolve_autonomy_level(
        channel_level="nonsense", workspace_level="autonomous"
    )
    assert level is AutonomyLevel.autonomous
