from agent.intake.models import Intent


def parse_classification(raw: str) -> Intent:
    """Parse the LLM response into an ``Intent`` (closed Enum).

    Pure function. Case and surrounding whitespace are ignored. Any unknown,
    empty or ambiguous label falls back to ``Intent.OTHER`` — the safe default.
    """
    normalized = raw.strip().lower()
    for intent in Intent:
        if intent.value == normalized:
            return intent
    return Intent.OTHER
