from agent.tools.base import ReadResult, ReadTool


class ReadToolRegistry:
    """Sélection structurée des outils de LECTURE (pas de boucle ReAct libre).

    Ne contient que des ``ReadTool`` (réversibles). Les actions d'écriture ne
    sont jamais des tools : elles n'existent que sous forme de ``ProposedAction``
    et ne peuvent donc structurellement pas entrer dans ce registre.
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
