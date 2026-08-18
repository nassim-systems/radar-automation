from pathlib import Path

from radar.eval import harness

MIN_HELDOUT_SIZE = 10
MAX_HELDOUT_SIZE = 20
MIN_LABEL = 0
MAX_LABEL = 10

HELDOUT_PATH = Path(harness.__file__).parent / "heldout_labeled.json"


def test_heldout_labeled_set_is_valid() -> None:
    dataset = harness.load_dataset(HELDOUT_PATH)

    assert MIN_HELDOUT_SIZE <= len(dataset) <= MAX_HELDOUT_SIZE
    for item in dataset:
        assert item.title.strip() != ""
        assert MIN_LABEL <= item.label <= MAX_LABEL
        assert "<img" not in item.title
