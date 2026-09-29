import hashlib

from agent.conversation.models import Turn
from agent.intake.models import InboundMessage
from core.sanitize import sanitize


def conversation_id_for(msg: InboundMessage) -> str:
    """Stable, deterministic thread identity.

    Same ``(channel, sender)`` (normalized) → same identifier. Pure
    function: depends only on the message, no state.
    """
    key = f"{msg.channel.strip().lower()}|{msg.sender.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_history_block(turns: list[Turn], max_turns: int) -> str:
    """Build a PURE history block, bounded to the last ``max_turns`` turns.

    Each turn (client AND agent) is sanitized via ``core.sanitize`` —
    idempotent and defense in depth. The format is structured
    (``<turn role="...">``): since ``sanitize`` strips every tag from the text,
    a client can neither forge a turn, nor mimic its role, nor close the
    block prematurely. Pure function: no mutation of ``turns``, no side effect.
    """
    recent = turns[-max_turns:] if max_turns > 0 else []
    lines = [
        f'<turn role="{turn.role.value}">{sanitize(turn.text)}</turn>'
        for turn in recent
    ]
    return "\n".join(lines)
