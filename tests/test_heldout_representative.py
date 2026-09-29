"""Guardrails on the representative held-out set (module 3.5).

Two distinct properties are tested:
- **sealed** (non-contamination): the JSON file structurally has no
  channel to carry a model score; only ``RawItem`` fields + a human
  ``label`` appear in it. A score therefore cannot have slipped in.
- **representativeness**: the label distribution covers the three intended
  tiers (off-topic / medium / highly relevant), and the set is disjoint
  from the training dataset (no train/held-out leak).
"""
import json
from pathlib import Path

from radar.eval.harness import load_dataset

REPO = Path(__file__).resolve().parents[1]
HELDOUT_PATH = REPO / "src" / "radar" / "eval" / "heldout_representative.json"
TRAINING_DATASET_PATH = REPO / "src" / "radar" / "eval" / "dataset.json"

MIN_HELDOUT_SIZE = 30
MAX_LABEL = 10
OFF_TOPIC_MAX = 2
MEDIUM_MIN = 5
MEDIUM_MAX = 6
HIGHLY_RELEVANT_MIN = 8
_ALLOWED_KEYS = {
    "source",
    "external_id",
    "title",
    "url",
    "published_at",
    "summary",
    "label",
}
_MIN_PER_BAND = 8  # tolerance below the actual 10/10/10, in case the set evolves


def _raw_items() -> list[dict[str, object]]:
    return json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))


def test_heldout_representative_has_expected_size() -> None:
    assert len(_raw_items()) >= MIN_HELDOUT_SIZE


def test_heldout_representative_is_sealed_no_model_score_field() -> None:
    # The schema admits only RawItem + a human label: no field can
    # carry a model score. Contamination is therefore structurally
    # impossible, not just a matter of author discipline.
    for raw in _raw_items():
        assert set(raw.keys()) <= _ALLOWED_KEYS
        assert "score" not in raw
        assert "model_score" not in raw
        assert "prediction" not in raw


def test_heldout_representative_is_valid_ground_truth() -> None:
    dataset = load_dataset(HELDOUT_PATH)

    assert len(dataset) >= MIN_HELDOUT_SIZE
    for item in dataset:
        assert item.title.strip() != ""
        assert 0 <= item.label <= MAX_LABEL


def test_heldout_representative_covers_all_three_relevance_bands() -> None:
    labels = [item["label"] for item in _raw_items()]

    n_off_topic = sum(1 for label in labels if 0 <= label <= OFF_TOPIC_MAX)
    n_medium = sum(1 for label in labels if MEDIUM_MIN <= label <= MEDIUM_MAX)
    n_highly_relevant = sum(
        1 for label in labels if HIGHLY_RELEVANT_MIN <= label <= MAX_LABEL
    )

    assert n_off_topic >= _MIN_PER_BAND
    assert n_medium >= _MIN_PER_BAND
    assert n_highly_relevant >= _MIN_PER_BAND
    # Gray zones (3-4, 7) deliberately avoided: clear tiers so that
    # precision/recall_at_threshold are not drowned in noise.
    assert n_off_topic + n_medium + n_highly_relevant == len(labels)


def test_heldout_representative_is_disjoint_from_training_dataset() -> None:
    training_raw = json.loads(TRAINING_DATASET_PATH.read_text(encoding="utf-8"))
    training_titles = {item["title"] for item in training_raw}
    heldout_titles = {item["title"] for item in _raw_items()}

    assert training_titles & heldout_titles == set()


def test_heldout_representative_has_unique_item_keys() -> None:
    keys = [(item["source"], item["external_id"]) for item in _raw_items()]

    assert len(keys) == len(set(keys))
