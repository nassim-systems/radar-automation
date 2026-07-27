from radar.drafting.parse import Draft, parse_draft


def test_parse_draft_strips_and_normalises() -> None:
    raw = "  \n\n  Ligne une.  \n\n\n  Ligne deux.  \n  "

    draft = parse_draft(raw)

    assert draft.text == "Ligne une.\nLigne deux."


def test_parse_draft_returns_draft_model() -> None:
    draft = parse_draft("Un brouillon.")

    assert isinstance(draft, Draft)
    assert draft.text == "Un brouillon."


def test_parse_draft_empty_response() -> None:
    assert parse_draft("   \n  ").text == ""
