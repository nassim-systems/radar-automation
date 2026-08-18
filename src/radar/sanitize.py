import re

_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")


def sanitize(text: str) -> str:
    """Neutralise un texte non fiable avant interpolation dans un prompt.

    Retire toute balise ``<...>`` — dont ``<article>`` et ``</article>`` — pour
    qu'un ``title``/``summary`` scrapé ne puisse pas refermer prématurément le
    bloc de données du prompt (breakout de délimiteur / injection). Normalise
    aussi les espaces résiduels.
    """
    return _WHITESPACE.sub(" ", _TAG.sub("", text)).strip()
