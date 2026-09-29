SCALE = 10


def agreement(predictions: list[int], labels: list[int]) -> float:
    """Measure agreement between predicted and human scores (0-10 scale).

    Why this metric
    ---------------
    Labels are human judgments on an ordinal 0-10 scale. Strict accuracy
    (exact match) would be too harsh: predicting 6 when the human said 7 is
    a near-agreement, not a binary error. So we use the magnitude of the
    disagreement rather than a mere equal/different boolean.

    What it measures
    ----------------
    We compute the mean absolute error (MAE) between predictions and
    labels, normalize it by the scale span (``SCALE`` = 10) and subtract it
    from 1:

        agreement = 1 - MAE / SCALE

    - 1.0 => identical scores (perfect agreement);
    - 0.0 => maximal disagreement (mean gap of 10 points).

    The result is bounded to [0, 1]: out-of-scale predictions cannot
    produce a negative agreement. The function is pure and deterministic, so
    fully reproducible without an API key.

    Conventions and safeguards
    --------------------------
    - An empty set contains no disagreement: agreement is 1.0.
    - Lists of different lengths are a programming error and raise
      ``ValueError``.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must have the same length")
    if not predictions:
        return 1.0
    total_error = sum(
        abs(pred - label)
        for pred, label in zip(predictions, labels, strict=True)
    )
    mae = total_error / len(predictions)
    return max(0.0, 1.0 - mae / SCALE)


def _average_ranks(values: list[float]) -> list[float]:
    """1-based ranks, averaged on ties."""
    ordered = sorted(values)
    rank_of: dict[float, float] = {}
    i = 0
    n = len(ordered)
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1] == ordered[i]:
            j += 1
        rank_of[ordered[i]] = (i + j) / 2 + 1
        i = j + 1
    return [rank_of[value] for value in values]


def spearman(predictions: list[int], labels: list[int]) -> float:
    """Spearman rank correlation between predictions and labels.

    Measures whether the order induced by the predicted scores follows that
    of the human labels: for a radar, the *ranking* matters, not the
    absolute value. Ties (numerous when the model saturates) are handled
    by average ranks. Result in [-1, 1]; by convention 0.0 if a series
    is constant (undefined correlation) or if the lists are empty.

    :raises ValueError: if the two lists differ in length.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must have the same length")
    n = len(predictions)
    if n == 0:
        return 0.0
    rank_pred = _average_ranks([float(x) for x in predictions])
    rank_label = _average_ranks([float(x) for x in labels])
    mean_pred = sum(rank_pred) / n
    mean_label = sum(rank_label) / n
    cov = sum(
        (rp - mean_pred) * (rl - mean_label)
        for rp, rl in zip(rank_pred, rank_label, strict=True)
    )
    var_pred = sum((rp - mean_pred) ** 2 for rp in rank_pred)
    var_label = sum((rl - mean_label) ** 2 for rl in rank_label)
    if var_pred == 0 or var_label == 0:
        return 0.0
    return cov / (var_pred * var_label) ** 0.5


def precision_at_threshold(
    predictions: list[int], labels: list[int], threshold: int
) -> float:
    """Precision of the ``score >= threshold`` gate (the one ``min_score`` uses).

    Among the items the model would **retain** at this threshold, what
    fraction is **truly relevant** according to the human label?

        precision = |retained ∩ relevant| / |retained|

    "Retained" = ``prediction >= threshold``; "relevant" = ``label >=
    threshold`` (same threshold on both sides: it is the question we ask
    ``min_score`` — if we only draft from this score up, are we right?).

    Convention: if the model retains no item at this threshold, precision
    is 1.0 — no false positive is possible (consistent with real usage:
    a ``min_score`` that drafts nothing is never a precision error, see
    ``run_pipeline``/``filter_by_min_score``).

    :raises ValueError: if the two lists differ in length.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must have the same length")
    retained_are_relevant = [
        label >= threshold
        for pred, label in zip(predictions, labels, strict=True)
        if pred >= threshold
    ]
    if not retained_are_relevant:
        return 1.0
    return sum(retained_are_relevant) / len(retained_are_relevant)


def recall_at_threshold(
    predictions: list[int], labels: list[int], threshold: int
) -> float:
    """Recall of the ``score >= threshold`` gate (the one ``min_score`` uses).

    Among the items **truly relevant** according to the human label, what
    fraction does the model **retain** at this threshold?

        recall = |retained ∩ relevant| / |relevant|

    Convention: if no item is truly relevant at this threshold, recall
    is 1.0 — nothing to retrieve, hence no false negative possible.

    :raises ValueError: if the two lists differ in length.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must have the same length")
    relevant_are_retained = [
        pred >= threshold
        for pred, label in zip(predictions, labels, strict=True)
        if label >= threshold
    ]
    if not relevant_are_retained:
        return 1.0
    return sum(relevant_are_retained) / len(relevant_are_retained)
