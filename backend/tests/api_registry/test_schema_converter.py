import json

from app.services.api_registry.schema_converter import endpoint_to_input_schema, rest_response_to_mcp_content


def test_endpoint_to_input_schema_builds_object_schema_from_parameters() -> None:
    parameters = {
        "id": {"type": "string", "required": True, "location": "path"},
        "verbose": {"type": "boolean", "required": False, "location": "query"},
    }

    schema = endpoint_to_input_schema(parameters)

    assert schema["type"] == "object"
    assert schema["properties"]["id"] == {"type": "string"}
    assert schema["properties"]["verbose"] == {"type": "boolean"}
    assert schema["required"] == ["id"]


def test_endpoint_to_input_schema_omits_required_key_when_nothing_required() -> None:
    schema = endpoint_to_input_schema({"q": {"type": "string", "required": False}})
    assert "required" not in schema


def test_endpoint_to_input_schema_includes_description_when_present() -> None:
    schema = endpoint_to_input_schema({"id": {"type": "string", "description": "Customer id"}})
    assert schema["properties"]["id"]["description"] == "Customer id"


def test_endpoint_to_input_schema_falls_back_to_string_for_unknown_types() -> None:
    schema = endpoint_to_input_schema({"weird": {"type": "not-a-json-schema-type"}})
    assert schema["properties"]["weird"]["type"] == "string"


def test_endpoint_to_input_schema_handles_empty_parameters() -> None:
    schema = endpoint_to_input_schema({})
    assert schema == {"type": "object", "properties": {}}


def test_rest_response_to_mcp_content_wraps_json_body_as_text() -> None:
    content = rest_response_to_mcp_content({"id": 123, "name": "John"})

    assert content["content"][0]["type"] == "text"
    assert json.loads(content["content"][0]["text"]) == {"id": 123, "name": "John"}


def test_rest_response_to_mcp_content_passes_through_plain_strings() -> None:
    content = rest_response_to_mcp_content("already a string")
    assert content["content"][0]["text"] == "already a string"
