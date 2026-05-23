"""Brave-backed web search tool."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx

from kortny.config import Settings, load_settings
from kortny.db.models import TaskEventType
from kortny.tools.types import JsonObject, JsonSchema, ToolResult

BRAVE_WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_RESULT_COUNT = 5
MAX_RESULT_COUNT = 20
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 1.05
RECOVERABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}
_GLOBAL_RATE_LIMIT_LOCK = threading.Lock()
_GLOBAL_LAST_REQUEST_AT: float | None = None


class TaskEventSink(Protocol):
    """Subset of TaskService needed for tool event emission."""

    def append_event(
        self,
        task: uuid.UUID,
        event_type: TaskEventType | str,
        payload: dict[str, Any] | None = None,
    ) -> object:
        """Append an event for a task."""


class WebSearchTool:
    """Search the public web with Brave Search."""

    name = "web_search"
    description = "Searches the public web and returns structured search results."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The web search query.",
            },
            "count": {
                "type": "integer",
                "description": "Number of web results to return.",
                "minimum": 1,
                "maximum": MAX_RESULT_COUNT,
                "default": DEFAULT_RESULT_COUNT,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        api_key: str,
        *,
        task_service: TaskEventSink | None = None,
        task_id: uuid.UUID | None = None,
        endpoint: str = BRAVE_WEB_SEARCH_ENDPOINT,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        min_request_interval_seconds: float = DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("BRAVE_SEARCH_API_KEY is required for web_search")
        if (task_service is None) != (task_id is None):
            raise ValueError("task_service and task_id must be provided together")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds cannot be negative")

        self.api_key = api_key
        self.task_service = task_service
        self.task_id = task_id
        self.endpoint = endpoint
        self.timeout = timeout
        self.transport = transport
        self.min_request_interval_seconds = min_request_interval_seconds
        self.monotonic = monotonic
        self.sleep = sleep

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        **kwargs: Any,
    ) -> WebSearchTool:
        """Create the tool from application settings."""

        resolved_settings = settings or load_settings()
        api_key = resolved_settings.brave_search_api_key
        if api_key is None:
            raise ValueError("BRAVE_SEARCH_API_KEY is required for web_search")
        return cls(api_key=api_key, **kwargs)

    def invoke(self, args: JsonObject) -> ToolResult:
        query = _require_query(args)
        count = _require_count(args)
        request_payload = {"query": query, "count": count}

        self._append_event(TaskEventType.tool_call, request_payload)
        try:
            response_payload = self._search(query=query, count=count)
        except httpx.HTTPStatusError as exc:
            output = _recoverable_http_error_output(query=query, response=exc.response)
            if output is None:
                raise
            self._append_error_result_event(query=query, error=output["error"])
            return ToolResult(output=output)
        except httpx.RequestError as exc:
            output = _recoverable_request_error_output(query=query, error=exc)
            self._append_error_result_event(query=query, error=output["error"])
            return ToolResult(output=output)

        results = _parse_results(response_payload)
        output = {
            "provider": "brave",
            "query": query,
            "results": results,
        }
        self._append_event(
            TaskEventType.tool_result,
            {
                "query": query,
                "result_count": len(results),
                "results": results,
            },
        )

        return ToolResult(output=output)

    def _search(self, *, query: str, count: int) -> JsonObject:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params: dict[str, str | int] = {
            "q": query,
            "count": count,
            "result_filter": "web",
        }

        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            self._pace_request()
            response = client.get(self.endpoint, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Brave Search response must be a JSON object")
        return payload

    def _pace_request(self) -> None:
        global _GLOBAL_LAST_REQUEST_AT

        if self.min_request_interval_seconds <= 0:
            return

        with _GLOBAL_RATE_LIMIT_LOCK:
            now = self.monotonic()
            if _GLOBAL_LAST_REQUEST_AT is not None:
                delay = self.min_request_interval_seconds - (
                    now - _GLOBAL_LAST_REQUEST_AT
                )
                if delay > 0:
                    self.sleep(delay)
                    now = self.monotonic()
            _GLOBAL_LAST_REQUEST_AT = now

    def _append_event(self, event_type: TaskEventType, payload: JsonObject) -> None:
        if self.task_service is None or self.task_id is None:
            return

        self.task_service.append_event(
            self.task_id,
            event_type,
            {"tool": self.name, **payload},
        )

    def _append_error_result_event(self, *, query: str, error: object) -> None:
        self._append_event(
            TaskEventType.tool_result,
            {
                "query": query,
                "result_count": 0,
                "error": error,
            },
        )


def _require_query(args: Mapping[str, Any]) -> str:
    query = args.get("query")
    if not isinstance(query, str) or query.strip() == "":
        raise ValueError("web_search requires a non-empty string 'query' argument")
    return query.strip()


def _require_count(args: Mapping[str, Any]) -> int:
    count = args.get("count", DEFAULT_RESULT_COUNT)
    if not isinstance(count, int):
        raise ValueError("web_search 'count' must be an integer")
    if count < 1 or count > MAX_RESULT_COUNT:
        raise ValueError(f"web_search 'count' must be between 1 and {MAX_RESULT_COUNT}")
    return count


def _parse_results(payload: JsonObject) -> list[JsonObject]:
    web = payload.get("web", {})
    if not isinstance(web, dict):
        return []

    raw_results = web.get("results", [])
    if not isinstance(raw_results, list):
        return []

    results: list[JsonObject] = []
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            continue

        title = _optional_string(raw_result.get("title"))
        url = _optional_string(raw_result.get("url"))
        snippet = _optional_string(raw_result.get("description"))
        if title is None or url is None:
            continue

        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet or "",
            }
        )

    return results


def _recoverable_http_error_output(
    *,
    query: str,
    response: httpx.Response,
) -> JsonObject | None:
    if response.status_code not in RECOVERABLE_HTTP_STATUS_CODES:
        return None

    retry_after = _optional_string(response.headers.get("Retry-After"))
    error: JsonObject = {
        "code": "rate_limited"
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS
        else "upstream_unavailable",
        "message": _recoverable_http_error_message(response.status_code),
        "recoverable": True,
        "status_code": response.status_code,
    }
    if retry_after is not None:
        error["retry_after"] = retry_after

    return _error_output(query=query, error=error)


def _recoverable_request_error_output(
    *,
    query: str,
    error: httpx.RequestError,
) -> JsonObject:
    return _error_output(
        query=query,
        error={
            "code": "request_failed",
            "message": f"Brave Search request failed temporarily: {type(error).__name__}",
            "recoverable": True,
        },
    )


def _error_output(*, query: str, error: JsonObject) -> JsonObject:
    return {
        "provider": "brave",
        "query": query,
        "results": [],
        "error": error,
    }


def _recoverable_http_error_message(status_code: int) -> str:
    if status_code == httpx.codes.TOO_MANY_REQUESTS:
        return "Brave Search rate limit was reached for this request."
    return f"Brave Search returned a temporary HTTP {status_code} response."


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
