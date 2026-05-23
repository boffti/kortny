"""A minimal tool used to prove the registry path."""

from __future__ import annotations

from kortny.tools.types import JsonObject, JsonSchema, ToolResult


class EchoTool:
    """Return the provided message unchanged."""

    name = "echo"
    description = "Echoes a message back unchanged."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message to echo.",
            }
        },
        "required": ["message"],
        "additionalProperties": False,
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        message = args.get("message")
        if not isinstance(message, str):
            raise ValueError("echo requires a string 'message' argument")

        return ToolResult(output={"message": message})
