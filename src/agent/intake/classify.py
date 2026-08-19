from agent.intake.models import InboundMessage, Intent
from agent.intake.parse import parse_classification
from agent.intake.prompt import build_classification_prompt
from radar.llm.base import LLMClient


def classify(msg: InboundMessage, llm: LLMClient) -> Intent:
    """Classe un message entrant en une ``Intent`` (lecture seule).

    Aucun effet de bord, aucun tool-use, aucun état global. La frontière LLM est
    isolée derrière ``llm`` (injecté). Toute réponse inconnue ou malformée
    retombe sur ``Intent.OTHER`` via ``parse_classification`` (défaut sûr).
    """
    prompt = build_classification_prompt(msg)
    return parse_classification(llm.complete(prompt))
