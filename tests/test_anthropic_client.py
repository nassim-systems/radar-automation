from types import SimpleNamespace
from unittest.mock import patch

from radar.llm.anthropic_client import MODEL, AnthropicClient
from radar.llm.pricing import estimate_cost
from radar.llm.usage import LlmUsage

INPUT_TOKENS = 100
OUTPUT_TOKENS = 20


def test_anthropic_client_complete_extracts_text() -> None:
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="7")])

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.return_value = response
        client = AnthropicClient()

        assert client.complete("un prompt") == "7"


def test_anthropic_client_returns_empty_without_text_block() -> None:
    response = SimpleNamespace(content=[])

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.return_value = response
        client = AnthropicClient()

        assert client.complete("un prompt") == ""


def test_anthropic_client_reports_usage_via_sink() -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="7")],
        usage=SimpleNamespace(
            input_tokens=INPUT_TOKENS, output_tokens=OUTPUT_TOKENS
        ),
    )

    class _FakeSink:
        def __init__(self) -> None:
            self.calls: list[LlmUsage] = []

        def record(self, usage: LlmUsage) -> None:
            self.calls.append(usage)

    sink = _FakeSink()

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.return_value = response
        client = AnthropicClient(usage_sink=sink)

        result = client.complete("un prompt")

    assert result == "7"  # le canal usage n'altère pas le retour existant
    assert len(sink.calls) == 1
    assert sink.calls[0].input_tokens == INPUT_TOKENS
    assert sink.calls[0].output_tokens == OUTPUT_TOKENS
    assert sink.calls[0].cost_usd == estimate_cost(MODEL, INPUT_TOKENS, OUTPUT_TOKENS)


def test_anthropic_client_without_sink_does_not_touch_usage() -> None:
    # aucune capacité .usage sur cette réponse : ne doit pas lever si
    # usage_sink n'est pas injecté (comportement par défaut, non-breaking).
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="7")])

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.return_value = response
        client = AnthropicClient()

        assert client.complete("un prompt") == "7"
