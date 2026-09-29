from radar.llm.fake import FakeLLM


class ScriptedFakeLLM(FakeLLM):
    """Scripted FakeLLM: picks the response based on the prompt content.

    Extends :class:`FakeLLM` (module 1.3) without modifying it. ``canned``
    remains the default response; ``mapping`` associates a prompt substring
    with a response. This allows testing ``evaluate`` without an API key,
    returning different scores depending on the item.
    """

    def __init__(self, canned: str, mapping: dict[str, str] | None = None) -> None:
        super().__init__(canned)
        self.mapping = mapping or {}

    def complete(self, prompt: str) -> str:
        for needle, response in self.mapping.items():
            if needle in prompt:
                return response
        return super().complete(prompt)
