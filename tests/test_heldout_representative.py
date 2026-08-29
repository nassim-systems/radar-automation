"""Garde-fous sur le held-out représentatif (module 3.5).

Deux propriétés distinctes sont testées :
- **scellé** (non-contamination) : le fichier JSON n'a structurellement aucun
  canal pour transporter un score modèle — seuls des champs ``RawItem`` + un
  ``label`` humain y figurent. Un score ne peut donc pas s'y être glissé.
- **représentativité** : la distribution des labels couvre bien les trois
  paliers voulus (hors-sujet / moyen / très pertinent), et le jeu est
  disjoint du dataset d'entraînement (pas de fuite train/held-out).
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
_MIN_PER_BAND = 8  # tolérance sous les 10/10/10 réels, au cas où le jeu évolue


def _raw_items() -> list[dict[str, object]]:
    return json.loads(HELDOUT_PATH.read_text(encoding="utf-8"))


def test_heldout_representative_has_expected_size() -> None:
    assert len(_raw_items()) >= MIN_HELDOUT_SIZE


def test_heldout_representative_is_sealed_no_model_score_field() -> None:
    # Le schéma n'admet que RawItem + label humain : aucun champ ne peut
    # transporter un score modèle. La contamination est donc structurellement
    # impossible, pas seulement une question de discipline d'auteur.
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
    # Zones grises (3-4, 7) volontairement évitées : paliers nets pour que
    # precision/recall_at_threshold ne soient pas noyés dans le bruit.
    assert n_off_topic + n_medium + n_highly_relevant == len(labels)


def test_heldout_representative_is_disjoint_from_training_dataset() -> None:
    training_raw = json.loads(TRAINING_DATASET_PATH.read_text(encoding="utf-8"))
    training_titles = {item["title"] for item in training_raw}
    heldout_titles = {item["title"] for item in _raw_items()}

    assert training_titles & heldout_titles == set()


def test_heldout_representative_has_unique_item_keys() -> None:
    keys = [(item["source"], item["external_id"]) for item in _raw_items()]

    assert len(keys) == len(set(keys))
