import re

_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")


def sanitize(text: str) -> str:
    """Neutralize untrusted text before interpolating it into a prompt.

    Single primitive shared by ``radar`` and ``agent``. Strips every
    ``<...>`` tag (including the ``<article>`` / ``<message>`` delimiters) so
    an injection cannot close the data block prematurely, and normalizes
    whitespace. Pure, read-only function.
    """
    return _WHITESPACE.sub(" ", _TAG.sub("", text)).strip()
