from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from anthropic import BadRequestError, OverloadedError, RateLimitError

from core.usage import LlmUsage
from radar.llm.anthropic_client import MODEL, AnthropicClient
from radar.llm.errors import TransientLLMError
from radar.llm.pricing import estimate_cost

INPUT_TOKENS = 100
OUTPUT_TOKENS = 20
_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


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

    assert result == "7"  # the usage channel does not alter the existing return value
    assert len(sink.calls) == 1
    assert sink.calls[0].input_tokens == INPUT_TOKENS
    assert sink.calls[0].output_tokens == OUTPUT_TOKENS
    assert sink.calls[0].cost_usd == estimate_cost(MODEL, INPUT_TOKENS, OUTPUT_TOKENS)


def test_anthropic_client_without_sink_does_not_touch_usage() -> None:
    # no .usage attribute on this response: must not raise if
    # usage_sink is not injected (default behavior, non-breaking).
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="7")])

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.return_value = response
        client = AnthropicClient()

        assert client.complete("un prompt") == "7"


def test_anthropic_client_translates_rate_limit_to_transient_error() -> None:
    original = RateLimitError(
        "rate limited",
        response=httpx.Response(status_code=429, request=_REQUEST),
        body=None,
    )

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.side_effect = original
        client = AnthropicClient()

        with pytest.raises(TransientLLMError) as exc_info:
            client.complete("un prompt")

    assert exc_info.value.__cause__ is original  # chain preserved (raise ... from)


def test_anthropic_client_translates_overloaded_to_transient_error() -> None:
    original = OverloadedError(
        "overloaded",
        response=httpx.Response(status_code=529, request=_REQUEST),
        body=None,
    )

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.side_effect = original
        client = AnthropicClient()

        with pytest.raises(TransientLLMError):
            client.complete("un prompt")


def test_anthropic_client_does_not_translate_non_transient_errors() -> None:
    # 400 Bad Request: not a transient error, must never become a
    # TransientLLMError (hence never retried by the retry policy).
    original = BadRequestError(
        "requête invalide",
        response=httpx.Response(status_code=400, request=_REQUEST),
        body=None,
    )

    with patch("radar.llm.anthropic_client.Anthropic") as anthropic_cls:
        anthropic_cls.return_value.messages.create.side_effect = original
        client = AnthropicClient()

        with pytest.raises(BadRequestError):
            client.complete("un prompt")
