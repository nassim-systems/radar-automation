SCALE = 10


def agreement(predictions: list[int], labels: list[int]) -> float:
    """Mesure l'accord entre scores prédits et scores humains (échelle 0-10).

    Pourquoi cette métrique
    -----------------------
    Les labels sont des jugements humains sur une échelle ordinale 0-10. Une
    exactitude stricte (exact match) serait trop sévère : prédire 6 quand
    l'humain a mis 7 est un quasi-accord, pas une erreur binaire. On exploite
    donc l'amplitude du désaccord plutôt qu'un simple booléen égal/différent.

    Ce qu'elle mesure
    -----------------
    On calcule l'erreur absolue moyenne (MAE) entre prédictions et labels, on
    la normalise par l'amplitude de l'échelle (``SCALE`` = 10) et on la
    retranche à 1 :

        agreement = 1 - MAE / SCALE

    - 1.0 => scores identiques (accord parfait) ;
    - 0.0 => désaccord maximal (écart moyen de 10 points).

    Le résultat est borné à [0, 1] : des prédictions hors échelle ne peuvent
    pas produire un accord négatif. La fonction est pure et déterministe, donc
    entièrement reproductible sans clé API.

    Conventions et garde-fous
    -------------------------
    - Un ensemble vide ne contient aucun désaccord : l'accord vaut 1.0.
    - Des listes de longueurs différentes sont une erreur de programmation et
      lèvent ``ValueError``.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions et labels doivent avoir la même longueur")
    if not predictions:
        return 1.0
    total_error = sum(
        abs(pred - label)
        for pred, label in zip(predictions, labels, strict=True)
    )
    mae = total_error / len(predictions)
    return max(0.0, 1.0 - mae / SCALE)


def _average_ranks(values: list[float]) -> list[float]:
    """Rangs 1-based, moyennés en cas d'égalité."""
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
    """Corrélation de rang de Spearman entre prédictions et labels.

    Mesure si l'ordre induit par les scores prédits suit celui des labels
    humains : pour un radar, c'est le *classement* qui compte, pas la valeur
    absolue. Les égalités (nombreuses quand le modèle plafonne) sont gérées
    par rangs moyens. Résultat dans [-1, 1] ; par convention 0.0 si une série
    est constante (corrélation indéfinie) ou si les listes sont vides.

    :raises ValueError: si les deux listes n'ont pas la même longueur.
    """
    if len(predictions) != len(labels):
        raise ValueError("predictions et labels doivent avoir la même longueur")
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
