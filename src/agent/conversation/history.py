import hashlib

from agent.conversation.models import Turn
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

    Chaque tour (client ET agent) est sanitizé via ``core.sanitize`` — idempotent
    et défense en profondeur. Le format est structuré (``<turn role="...">``) :
    comme ``sanitize`` retire toute balise du texte, un client ne peut ni forger
    un tour, ni en imiter le rôle, ni refermer le bloc prématurément. Fonction
    pure : aucune mutation de ``turns``, aucun effet de bord.
    """
    recent = turns[-max_turns:] if max_turns > 0 else []
    lines = [
        f'<turn role="{turn.role.value}">{sanitize(turn.text)}</turn>'
        for turn in recent
    ]
    return "\n".join(lines)
