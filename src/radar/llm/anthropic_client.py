from anthropic import Anthropic, OverloadedError, RateLimitError

from core.usage import LlmUsage, UsageSink
from radar.llm.errors import TransientLLMError
from radar.llm.pricing import estimate_cost

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 16  # enough for scoring (one integer); drafting needs more
# Erreurs traduites en TransientLLMError (module 4.3) : rate limit (429) et
# overload (529) only — explicit choice documented in CONCURRENCY.md,
# which deliberately excludes generic 5xx (InternalServerError).
_RETRIABLE_ANTHROPIC_ERRORS = (RateLimitError, OverloadedError)


class AnthropicClient:
    """Real adapter implementing ``LLMClient`` via the Anthropic API (Haiku 4.5).

    The API key is never hard-coded. ``api_key`` may be injected by the
    composition root (from the environment via ``Settings``); if it is
    ``None``, the SDK resolves it from the environment itself. ``max_tokens``
    is tunable: the default suffices for scoring, drafting needs more.
    ``usage_sink``, if injected, is notified of the real usage (tokens +
    cost) after each call — ``complete`` keeps returning a ``str`` (no
    existing caller, scoring/drafting/agent, is affected).
    """

    def __init__(
        self,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        api_key: str | None = None,
        usage_sink: UsageSink | None = None,
    ) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._usage_sink = usage_sink

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except _RETRIABLE_ANTHROPIC_ERRORS as error:
            raise TransientLLMError(str(error)) from error
        if self._usage_sink is not None:
            self._usage_sink.record(
                LlmUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cost_usd=estimate_cost(
                        self._model,
                        response.usage.input_tokens,
                        response.usage.output_tokens,
                    ),
                )
            )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
