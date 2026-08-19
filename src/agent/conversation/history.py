import hashlib

from agent.conversation.models import Role, Turn
from agent.intake.models import InboundMessage
from core.sanitize import sanitize


def conversation_id_for(msg: InboundMessage) -> str:
    """Identité de fil stable et déterministe.

    Même ``(canal, expéditeur)`` (normalisés) → même identifiant. Fonction
    pure : ne dépend que du message, aucun état.
    """
    key = f"{msg.channel.strip().lower()}|{msg.sender.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_history_block(turns: list[Turn], max_turns: int) -> str:
    """Construit un bloc d'historique PUR, borné aux ``max_turns`` derniers tours.

    Chaque tour CLIENT est sanitizé (donnée non fiable) via ``core.sanitize`` ;
    les tours AGENT (sorties maîtrisées) sont conservés tels quels. Fonction
    pure : aucune mutation de ``turns``, aucun effet de bord.
    """
    recent = turns[-max_turns:] if max_turns > 0 else []
    lines: list[str] = []
    for turn in recent:
        text = sanitize(turn.text) if turn.role == Role.CLIENT else turn.text
        lines.append(f"[{turn.role.value}] {text}")
    return "\n".join(lines)
