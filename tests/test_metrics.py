import pytest

from radar.eval.metrics import agreement

PERFECT_AGREEMENT = 1.0


def test_agreement_is_perfect_when_scores_match() -> None:
    assert agreement([3, 7, 0], [3, 7, 0]) == PERFECT_AGREEMENT


def test_agreement_reflects_average_distance() -> None:
    # ecart moyen de 2 points sur 10 -> 1 - 0.2 = 0.8
    assert agreement([5, 5], [7, 3]) == pytest.approx(0.8)


def test_agreement_is_zero_for_maximal_distance() -> None:
    assert agreement([0, 0], [10, 10]) == pytest.approx(0.0)


def test_agreement_never_goes_negative() -> None:
    # prediction hors echelle : la borne basse reste 0.0
    assert agreement([50], [0]) == pytest.approx(0.0)


def test_agreement_raises_on_length_mismatch() -> None:
    with pytest.raises(ValueError):
        agreement([1, 2], [1])
