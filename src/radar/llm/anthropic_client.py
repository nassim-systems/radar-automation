from anthropic import Anthropic

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 16  # suffit au scoring (un entier) ; le drafting en demande plus


class AnthropicClient:
    """Adaptateur réel implémentant ``LLMClient`` via l'API Anthropic (Haiku 4.5).

    La clé API n'est jamais codée en dur. ``api_key`` peut être injecté par la
    racine de composition (depuis l'environnement via ``Settings``) ; s'il vaut
    ``None``, le SDK la résout lui-même depuis l'environnement. ``max_tokens``
    est réglable : la valeur par défaut suffit au scoring, le drafting demande
    davantage.
    """

    def __init__(
        self,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        api_key: str | None = None,
    ) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
