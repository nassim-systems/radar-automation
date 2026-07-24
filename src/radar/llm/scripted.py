from radar.llm.fake import FakeLLM


class ScriptedFakeLLM(FakeLLM):
    """FakeLLM scénarisé : choisit la réponse selon le contenu du prompt.

    Étend :class:`FakeLLM` (module 1.3) sans le modifier. ``canned`` reste la
    réponse par défaut ; ``mapping`` associe une sous-chaîne du prompt à une
    réponse. Cela permet de tester ``evaluate`` sans clé API, en renvoyant des
    scores différents selon l'item.
    """

    def __init__(self, canned: str, mapping: dict[str, str] | None = None) -> None:
        super().__init__(canned)
        self.mapping = mapping or {}

    def complete(self, prompt: str) -> str:
        for needle, response in self.mapping.items():
            if needle in prompt:
                return response
        return super().complete(prompt)
