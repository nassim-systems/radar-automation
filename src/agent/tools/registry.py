from agent.tools.base import ReadResult, ReadTool


class ReadToolRegistry:
    """Structured selection of READ tools (no free ReAct loop).

    Contains only ``ReadTool``s (reversible). Write actions are never tools:
    they exist only as ``ProposedAction`` and so structurally cannot enter
    this registry.
    """

    def __init__(self, tools: list[ReadTool]) -> None:
        self._tools: dict[str, ReadTool] = {tool.name: tool for tool in tools}

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ReadTool | None:
        return self._tools.get(name)

    def read(self, name: str, query: str) -> ReadResult:
        tool = self._tools.get(name)
        if tool is None:
            return ReadResult(tool=name, ok=False, data="")
        return tool.read(query)
