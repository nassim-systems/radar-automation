class UnknownModelPricingError(Exception):
    """Levée quand aucun tarif n'est connu pour le modèle demandé."""


# USD par million de tokens (input, output). Grille tarifaire par modèle —
# jamais un coût en dur dans le code appelant.
_PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus-4-5": (15.00, 75.00),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Coût USD estimé d'un appel, à partir de la grille tarifaire par modèle.

    Fonction pure. Lève ``UnknownModelPricingError`` pour un modèle sans tarif
    connu — fail-fast plutôt qu'un coût silencieusement erroné (ex. zéro).
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
