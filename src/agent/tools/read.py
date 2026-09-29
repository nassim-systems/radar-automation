from agent.tools.base import ReadResult


class CrmReadTool:
    """Look up a customer record by email — read-only, no LLM."""

    name = "crm_lookup"
    description = "Recherche une fiche client par email."

    def __init__(self, records: dict[str, str]) -> None:
        self._records = records

    def read(self, query: str) -> ReadResult:
        data = self._records.get(query, "")
        return ReadResult(tool=self.name, ok=bool(data), data=data)


class KnowledgeBaseReadTool:
    """Keyword search in the knowledge base — read-only."""

    name = "kb_search"
    description = "Keyword search in the knowledge base."

    def __init__(self, articles: dict[str, str]) -> None:
        self._articles = articles

    def read(self, query: str) -> ReadResult:
        needle = query.lower()
        for key, content in self._articles.items():
            if needle in key.lower():
                return ReadResult(tool=self.name, ok=True, data=content)
        return ReadResult(tool=self.name, ok=False, data="")
