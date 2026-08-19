from pydantic import BaseModel

from agent.intake.models import Intent

# Marqueur d'escalade : le modèle le place en tête quand une info manque.
ESCALATION_MARKER = "[ESCALADE]"


class ClientContext(BaseModel):
    client_name: str | None
    history_summary: str | None
    known_facts: list[str]


class DraftReply(BaseModel):
    text: str
    intent: Intent
    needs_human_facts: bool
