from anthropic import Anthropic

from radar.llm.pricing import estimate_cost
from radar.llm.usage import LlmUsage, UsageSink

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 16  # suffit au scoring (un entier) ; le drafting en demande plus


class AnthropicClient:
    """Adaptateur réel implémentant ``LLMClient`` via l'API Anthropic (Haiku 4.5).

    La clé API n'est jamais codée en dur. ``api_key`` peut être injecté par la
    racine de composition (depuis l'environnement via ``Settings``) ; s'il vaut
    ``None``, le SDK la résout lui-même depuis l'environnement. ``max_tokens``
    est réglable : la valeur par défaut suffit au scoring, le drafting demande
    davantage. ``usage_sink``, s'il est injecté, est notifié de l'usage réel
    (tokens + coût) après chaque appel — ``complete`` continue de renvoyer un
    ``str`` (aucun appelant existant, scoring/drafting/agent, n'est impacté).
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
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
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
