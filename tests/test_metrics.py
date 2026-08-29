import pytest

from radar.eval.metrics import (
    agreement,
    precision_at_threshold,
    recall_at_threshold,
    spearman,
)

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


def test_spearman_perfect_positive() -> None:
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)


def test_spearman_perfect_negative() -> None:
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_is_rank_based_not_linear() -> None:
    # relation monotone non lineaire -> correlation de rang parfaite
    assert spearman([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)


def test_spearman_handles_ties() -> None:
    # egalites gerees par rangs moyens
    assert spearman([1, 1, 2], [1, 1, 2]) == pytest.approx(1.0)


def test_spearman_zero_for_constant_series() -> None:
    # variance nulle -> correlation indefinie, convention 0.0
    assert spearman([5, 5, 5], [1, 2, 3]) == pytest.approx(0.0)


def test_spearman_raises_on_length_mismatch() -> None:
    with pytest.raises(ValueError):
        spearman([1, 2], [1])


def test_precision_at_threshold_perfect_when_all_retained_are_relevant() -> None:
    # retenus (pred>=6) : items 0 et 2, tous deux label>=6 -> precision 1.0
    predictions = [8, 3, 7, 2]
    labels = [9, 1, 6, 0]

    assert precision_at_threshold(predictions, labels, threshold=6) == pytest.approx(
        1.0
    )


def test_precision_at_threshold_penalises_false_positives() -> None:
    # retenus (pred>=6) : items 0 (label 9, pertinent) et 1 (label 2, pas pertinent)
    predictions = [8, 6]
    labels = [9, 2]

    assert precision_at_threshold(predictions, labels, threshold=6) == pytest.approx(
        0.5
    )


def test_precision_at_threshold_is_one_when_nothing_retained() -> None:
    # aucun item ne passe le seuil -> aucun faux positif possible (convention)
    predictions = [1, 2, 3]
    labels = [9, 9, 9]

    assert precision_at_threshold(predictions, labels, threshold=6) == pytest.approx(
        1.0
    )


def test_precision_at_threshold_raises_on_length_mismatch() -> None:
    with pytest.raises(ValueError):
        precision_at_threshold([1, 2], [1], threshold=6)


def test_recall_at_threshold_perfect_when_all_relevant_are_retained() -> None:
    # pertinents (label>=6) : items 0 et 2, tous deux pred>=6 -> recall 1.0
    predictions = [8, 3, 7, 2]
    labels = [9, 1, 6, 0]

    assert recall_at_threshold(predictions, labels, threshold=6) == pytest.approx(1.0)


def test_recall_at_threshold_penalises_false_negatives() -> None:
    # pertinents (label>=6) : items 0 (retenu, pred 8) et 1 (manqué, pred 2)
    predictions = [8, 2]
    labels = [9, 6]

    assert recall_at_threshold(predictions, labels, threshold=6) == pytest.approx(0.5)


def test_recall_at_threshold_is_one_when_nothing_relevant() -> None:
    # aucun item n'est vraiment pertinent -> rien à manquer (convention)
    predictions = [9, 9, 9]
    labels = [1, 2, 3]

    assert recall_at_threshold(predictions, labels, threshold=6) == pytest.approx(1.0)


def test_recall_at_threshold_raises_on_length_mismatch() -> None:
    with pytest.raises(ValueError):
        recall_at_threshold([1, 2], [1], threshold=6)
