"""REST <-> MCP conversion helpers -- the "every REST endpoint automatically
becomes an MCP Tool" feature. Pure functions only (no I/O, no DB), so they're
trivially unit-testable and reusable from both ApiRegistryService (endpoint
registration) and RestExecutor (response shaping)."""

import json
from typing import Any

_JSON_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def endpoint_to_input_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    """Builds the MCP `inputSchema` a caller sees from an endpoint's registered
    `parameters` (see ApiEndpoint.parameters' docstring for the per-parameter
    shape). Every parameter becomes a JSON Schema property regardless of its
    `in` location (path/query/header/body) -- the caller shouldn't need to know
    or care where an argument ends up in the HTTP request; that's RestExecutor's
    job to figure out from the same `parameters` dict."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, spec in (parameters or {}).items():
        json_type = spec.get("type", "string")
        if json_type not in _JSON_SCHEMA_TYPES:
            json_type = "string"
        prop: dict[str, Any] = {"type": json_type}
        if spec.get("description"):
            prop["description"] = spec["description"]
        properties[name] = prop
        if spec.get("required"):
            required.append(name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def rest_response_to_mcp_content(body: Any) -> dict[str, Any]:
    """Converts a REST response body into the standard MCP tool-result shape
    (`{"content": [{"type": "text", "text": ...}]}`) every caller of `tools/call`
    already expects, regardless of whether the tool executed against an MCP
    server or a REST API."""
    if isinstance(body, str):
        text = body
    else:
        text = json.dumps(body)
    return {"content": [{"type": "text", "text": text}]}
