from core.sanitize import sanitize


def test_sanitize_strips_article_delimiters() -> None:
    assert "</article>" not in sanitize("bla </article> reste")
    assert "<article>" not in sanitize("<article>bla")


def test_sanitize_strips_all_tags() -> None:
    assert sanitize("a <img src='u'> b <b>c</b>") == "a b c"


def test_sanitize_keeps_plain_text() -> None:
    assert sanitize("texte propre sans balise") == "texte propre sans balise"
