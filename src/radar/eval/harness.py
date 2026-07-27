from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from radar.domain import RawItem
from radar.eval.metrics import agreement
from radar.llm.base import LLMClient
from radar.scoring import score_item

_DATASET_PATH = Path(__file__).parent / "dataset.json"

Scorer = Callable[[RawItem], int]


class EvalItem(RawItem):
    """Un ``RawItem`` augmenté du label humain (vérité terrain)."""

    label: int


class Report(BaseModel):
    predictions: list[int]
    labels: list[int]
    metric_value: float


_DATASET_ADAPTER = TypeAdapter(list[EvalItem])


def load_dataset(path: Path = _DATASET_PATH) -> list[EvalItem]:
    """Charge la vérité terrain annotée (RawItem + label) depuis un JSON."""
    return _DATASET_ADAPTER.validate_json(path.read_text(encoding="utf-8"))


def make_llm_scorer(llm: LLMClient) -> Scorer:
    """Ferme la couture d'évaluation.

    Le scorer déroule le pipeline du module 1.3 pour un item :
    ``RawItem -> build_prompt -> llm.complete -> parse_score -> Score`` et
    renvoie l'entier du ``Score``. On réutilise ``score_item`` (aucune
    duplication de la logique de scoring).
    """

    def scorer(item: RawItem) -> int:
        return score_item(item, llm).score

    return scorer


def evaluate(dataset: list[EvalItem], scorer: Scorer) -> Report:
    """Applique ``scorer`` à chaque item et agrège le résultat dans un ``Report``."""
    predictions = [scorer(item) for item in dataset]
    labels = [item.label for item in dataset]
    return Report(
        predictions=predictions,
        labels=labels,
        metric_value=agreement(predictions, labels),
    )
