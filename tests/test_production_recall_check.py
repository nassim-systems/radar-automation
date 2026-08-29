"""Garde-fous sur le jeu de contrôle « rappel réel » (module 3.5, point 4).

Substitut au batch exact des 20 items du run réel de 3.3 (non conservé) :
20 items réels, les plus récents non sélectionnés dans le held-out de
calibration, donc un échantillon non biaisé plutôt qu'une seconde curation.
Mêmes garanties de non-contamination que ``heldout_representative.json``.
"""
import json
from pathlib import Path

from radar.eval.harness import load_dataset

REPO = Path(__file__).resolve().parents[1]
CHECK_PATH = REPO / "src" / "radar" / "eval" / "production_recall_check.json"
TRAINING_DATASET_PATH = REPO / "src" / "radar" / "eval" / "dataset.json"
HELDOUT_PATH = REPO / "src" / "radar" / "eval" / "heldout_representative.json"

EXPECTED_SIZE = 20
MAX_LABEL = 10
_ALLOWED_KEYS = {
    "source",
    "external_id",
    "title",
    "url",
    "published_at",
    "summary",
    "label",
}


def _raw_items() -> list[dict[str, object]]:
    return json.loads(CHECK_PATH.read_text(encoding="utf-8"))


def test_production_recall_check_has_expected_size() -> None:
    assert len(_raw_items()) == EXPECTED_SIZE


def test_production_recall_check_is_sealed_no_model_score_field() -> None:
    for raw in _raw_items():
        assert set(raw.keys()) <= _ALLOWED_KEYS
        assert "score" not in raw
        assert "model_score" not in raw
        assert "prediction" not in raw


def test_production_recall_check_is_valid_ground_truth() -> None:
    dataset = load_dataset(CHECK_PATH)

    assert len(dataset) == EXPECTED_SIZE
    for item in dataset:
        assert item.title.strip() != ""
        assert 0 <= item.label <= MAX_LABEL


def test_production_recall_check_is_disjoint_from_training_dataset() -> None:
    training_raw = json.loads(TRAINING_DATASET_PATH.read_text(encoding="utf-8"))
    training_titles = {item["title"] for item in training_raw}
    check_titles = {item["title"] for item in _raw_items()}

    assert training_titles & check_titles == set()


def test_production_recall_check_is_disjoint_from_calibration_heldout() -> None:
    # Échantillon non biaisé distinct du jeu curé pour la calibration : pas
    # de double-comptage entre les deux mesures.
    heldout_raw = json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))
    heldout_urls = {item["url"] for item in heldout_raw}
    check_urls = {item["url"] for item in _raw_items()}

    assert heldout_urls & check_urls == set()


def test_production_recall_check_has_unique_item_keys() -> None:
    keys = [(item["source"], item["external_id"]) for item in _raw_items()]

    assert len(keys) == len(set(keys))
