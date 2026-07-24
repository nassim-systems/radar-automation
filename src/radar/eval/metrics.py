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
