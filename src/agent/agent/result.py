from pydantic import BaseModel

from agent.intake.models import Intent
from agent.reply.models import DraftReply
from agent.tools.base import ProposedAction


class AgentResult(BaseModel):
    intent: Intent
    draft: DraftReply
    proposed_actions: list[ProposedAction]
    conversation_id: str
    tools_consulted: list[str]
    escalated: bool
