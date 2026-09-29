from agent.intake.models import InboundMessage, Intent
from agent.intake.parse import parse_classification
from agent.intake.prompt import build_classification_prompt
from radar.llm.base import LLMClient


def classify(msg: InboundMessage, llm: LLMClient) -> Intent:
    """Classify an incoming message into an ``Intent`` (read-only).

    No side effect, no tool use, no global state. The LLM boundary is
    isolated behind ``llm`` (injected). Any unknown or malformed response
    falls back to ``Intent.OTHER`` via ``parse_classification`` (safe default).
    """
    prompt = build_classification_prompt(msg)
    return parse_classification(llm.complete(prompt))
