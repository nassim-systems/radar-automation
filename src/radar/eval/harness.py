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
    """A ``RawItem`` augmented with the human label (ground truth)."""

    label: int


class Report(BaseModel):
    predictions: list[int]
    labels: list[int]
    metric_value: float


_DATASET_ADAPTER = TypeAdapter(list[EvalItem])


def load_dataset(path: Path = _DATASET_PATH) -> list[EvalItem]:
    """Load the annotated ground truth (RawItem + label) from a JSON."""
    return _DATASET_ADAPTER.validate_json(path.read_text(encoding="utf-8"))


def make_llm_scorer(llm: LLMClient) -> Scorer:
    """Close the evaluation seam.

    The scorer runs the module 1.3 pipeline for an item:
    ``RawItem -> build_prompt -> llm.complete -> parse_score -> Score`` and
    returns the ``Score`` integer. Reuses ``score_item`` (no duplication of
    the scoring logic).
    """

    def scorer(item: RawItem) -> int:
        return score_item(item, llm).score

    return scorer


def evaluate(dataset: list[EvalItem], scorer: Scorer) -> Report:
    """Apply ``scorer`` to each item and aggregate the result into a ``Report``."""
    predictions = [scorer(item) for item in dataset]
    labels = [item.label for item in dataset]
    return Report(
        predictions=predictions,
        labels=labels,
        metric_value=agreement(predictions, labels),
    )
