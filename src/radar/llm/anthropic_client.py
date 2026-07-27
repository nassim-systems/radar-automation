from anthropic import Anthropic

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 16


class AnthropicClient:
    """Adaptateur réel implémentant ``LLMClient`` via l'API Anthropic (Haiku 4.5).

    La clé API est résolue par le SDK depuis l'environnement
    (``ANTHROPIC_API_KEY``) ou un profil d'authentification ; elle n'est jamais
    codée en dur ni manipulée ici. Le prompt est construit par ``build_prompt``
    (module 1.3) et demande un entier ; ``complete`` renvoie le texte brut du
    modèle, que ``parse_score`` transforme en ``Score``.
    """

    def __init__(self, model: str = MODEL) -> None:
        self._client = Anthropic()
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
