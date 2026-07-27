from pydantic import BaseModel


class Draft(BaseModel):
    text: str


def parse_draft(response: str) -> Draft:
    """Nettoie et structure le brouillon renvoyé par le LLM.

    Fonction pure : retire les espaces superflus, supprime les lignes vides et
    normalise les fins de ligne, puis encapsule le texte dans un ``Draft``.
    """
    lines = [line.strip() for line in response.strip().splitlines()]
    text = "\n".join(line for line in lines if line)
    return Draft(text=text)
