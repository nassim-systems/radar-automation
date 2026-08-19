import re

_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")


def sanitize(text: str) -> str:
    """Neutralise un texte non fiable avant interpolation dans un prompt.

    Primitive unique partagée par ``radar`` et ``agent``. Retire toute balise
    ``<...>`` (dont les délimiteurs ``<article>`` / ``<message>``) pour empêcher
    une injection de refermer prématurément le bloc de données, et normalise les
    espaces. Fonction pure, lecture seule.
    """
    return _WHITESPACE.sub(" ", _TAG.sub("", text)).strip()
