from pydantic import BaseModel

from agent.intake.models import Intent

# Escalation marker: the model puts it first when info is missing.
ESCALATION_MARKER = "[ESCALADE]"


class ClientContext(BaseModel):
    client_name: str | None
    history_summary: str | None
    known_facts: list[str]


class DraftReply(BaseModel):
    text: str
    intent: Intent
    needs_human_facts: bool
