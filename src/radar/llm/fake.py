class FakeLLM:
    def __init__(self, canned: str) -> None:
        self.canned = canned

    def complete(self, prompt: str) -> str:
        return self.canned
