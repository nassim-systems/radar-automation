import pytest

from radar.llm.pricing import UnknownModelPricingError, estimate_cost


def test_estimate_cost_known_model_one_million_tokens_each() -> None:
    # claude-haiku-4-5 : 1.00 $/MTok input, 5.00 $/MTok output (grille pricing.py)
    cost = estimate_cost(
        "claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000
    )

    assert cost == pytest.approx(6.00)


def test_estimate_cost_zero_tokens_is_free() -> None:
    assert estimate_cost("claude-haiku-4-5", input_tokens=0, output_tokens=0) == 0.0


def test_estimate_cost_scales_linearly_with_tokens() -> None:
    cost = estimate_cost("claude-haiku-4-5", input_tokens=500_000, output_tokens=0)

    assert cost == pytest.approx(0.50)


def test_estimate_cost_uses_separate_input_output_prices() -> None:
    input_only = estimate_cost(
        "claude-haiku-4-5", input_tokens=100_000, output_tokens=0
    )
    output_only = estimate_cost(
        "claude-haiku-4-5", input_tokens=0, output_tokens=100_000
    )

    assert input_only != output_only  # distinct rates: no single hard-coded cost
    assert input_only == pytest.approx(0.10)
    assert output_only == pytest.approx(0.50)


def test_estimate_cost_unknown_model_raises() -> None:
    with pytest.raises(UnknownModelPricingError):
        estimate_cost("modele-inconnu", input_tokens=100, output_tokens=100)
