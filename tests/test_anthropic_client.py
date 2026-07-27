from types import SimpleNamespace
from unittest.mock import patch

from radar.llm.anthropic_client import AnthropicClient


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
