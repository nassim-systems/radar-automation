from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from radar.eval.metrics import agreement

_DATASET_PATH = Path(__file__).parent / "dataset.json"

Scorer = Callable[[str], int]


class EvalItem(BaseModel):
    text: str
    label: int


class Report(BaseModel):
    predictions: list[int]
    labels: list[int]
    metric_value: float


_DATASET_ADAPTER = TypeAdapter(list[EvalItem])


def load_dataset(path: Path = _DATASET_PATH) -> list[EvalItem]:
    """Charge la vérité terrain annotée à la main depuis un fichier JSON."""
    return _DATASET_ADAPTER.validate_json(path.read_text(encoding="utf-8"))


def evaluate(dataset: list[EvalItem], scorer: Scorer) -> Report:
    """Applique ``scorer`` à chaque item et agrège le résultat dans un ``Report``.

    ``scorer`` prend le texte d'un item et renvoie un score entier prédit. Le
    harness reste agnostique du modèle : en test on lui passe un scorer basé sur
    ``FakeLLM``/``ScriptedFakeLLM``, en production un scorer basé sur le vrai
    client LLM (module 1.4+, hors tests).
    """
    predictions = [scorer(item.text) for item in dataset]
    labels = [item.label for item in dataset]
    return Report(
        predictions=predictions,
        labels=labels,
        metric_value=agreement(predictions, labels),
    )
