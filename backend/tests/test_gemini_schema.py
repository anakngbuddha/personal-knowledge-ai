"""Gemini tool-schema normalisation and 400 recovery. No network."""

from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.llm.gemini import GeminiLLMProvider, _gemini_tools
from app.tools.registry import default_definitions
from app.tools.schema import ToolCall, ToolDefinition, ToolResult


def _assert_gemini_valid(node: dict) -> None:
    kind = node.get("type")
    if kind == "OBJECT":
        assert node.get("properties"), node
        for child in node["properties"].values():
            _assert_gemini_valid(child)
        for name in node.get("required", []):
            assert name in node["properties"], (name, node)
    if kind == "ARRAY":
        assert isinstance(node.get("items"), dict), node
        _assert_gemini_valid(node["items"])


def test_native_tool_schemas_are_gemini_valid():
    declarations = _gemini_tools(default_definitions())["functionDeclarations"]
    assert declarations
    for declaration in declarations:
        if "parameters" in declaration:
            _assert_gemini_valid(declaration["parameters"])


def test_bare_array_and_free_object_are_repaired():
    tool = ToolDefinition(
        name="fill",
        description="d",
        parameters={
            "type": "object",
            "properties": {"fields": {"type": "array"}, "opts": {"type": "object"}},
            "required": ["fields", "not_declared"],
            "additionalProperties": True,
        },
    )
    params = _gemini_tools([tool])["functionDeclarations"][0]["parameters"]
    assert params["properties"]["fields"]["items"] == {"type": "STRING"}
    assert params["properties"]["opts"]["type"] == "STRING"
    assert params["required"] == ["fields"]


def test_no_argument_tool_omits_parameters():
    tool = ToolDefinition(name="snapshot", description="d", parameters={"type": "object", "properties": {}})
    assert "parameters" not in _gemini_tools([tool])["functionDeclarations"][0]


def test_400_on_tool_request_retries_without_tools(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_base", "https://example.test/v1beta")
    provider = GeminiLLMProvider(api_key="k", model="gemini-test")
    payloads: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        payloads.append(json)
        response = MagicMock()
        if len(payloads) == 1:
            response.status_code = 400
            response.text = "bad function declaration"
        else:
            response.status_code = 200
            response.text = ""
            response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        return response

    tool = ToolDefinition(
        name="lookup", description="find",
        parameters={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    with patch("app.llm.gemini.httpx.post", fake_post), patch("app.llm.gemini.acquire_gemini"):
        answer = provider.generate_grounded_answer("q", [], system_prompt="s", tools=[tool])

    assert answer.text == "ok"
    assert "tools" in payloads[0]
    assert "tools" not in payloads[1]


def test_synthesis_without_tools_sends_results_as_text():
    provider = GeminiLLMProvider(api_key="k", model="gemini-test")
    payload = provider._build_payload(
        "q", [], "s", [{"role": "user", "content": ""}],
        tools=None,
        prior_tool_calls=[ToolCall(id="call_1", name="lookup", arguments={"q": "x"})],
        tool_results=[ToolResult(id="call_1", name="lookup", content={"hits": [1]})],
    )
    parts = [part for turn in payload["contents"] for part in turn["parts"]]
    assert not any("functionCall" in part or "functionResponse" in part for part in parts)
    assert any("lookup" in part.get("text", "") for part in parts)
    assert all(part.get("text", "x") for part in parts)
