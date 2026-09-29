class UnknownModelPricingError(Exception):
    """Raised when no price is known for the requested model."""


# USD per million tokens (input, output). Per-model price grid —
# never a hard-coded cost in the calling code.
_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus-4-5": (15.00, 75.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost of a call, from the per-model price grid.

    Pure function. Raises ``UnknownModelPricingError`` for a model with no
    known price — fail-fast rather than a silently wrong cost (e.g. zero).
    """
    try:
        input_price, output_price = _PRICING_USD_PER_MTOK[model]
    except KeyError as error:
        raise UnknownModelPricingError(
            f"aucun tarif connu pour le modèle : {model}"
        ) from error
    return (input_tokens / 1_000_000) * input_price + (
        output_tokens / 1_000_000
    ) * output_price
