import re

_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")


def sanitize(body: str) -> str:
    """Neutralise le corps d'un message avant interpolation dans un prompt.

    Retire toute balise ``<...>`` (dont les délimiteurs ``<message>`` /
    ``</message>``) pour empêcher une injection de refermer prématurément le
    bloc de données, et normalise les espaces. Fonction pure, lecture seule.
    """
    return _WHITESPACE.sub(" ", _TAG.sub("", body)).strip()
