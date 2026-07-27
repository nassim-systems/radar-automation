from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from radar.domain import RawItem
from radar.eval.harness import (
    EvalItem,
    Report,
    evaluate,
    load_dataset,
    make_llm_scorer,
)
from radar.llm.scripted import ScriptedFakeLLM

MIN_DATASET_SIZE = 20
MIN_LABEL = 0
MAX_LABEL = 10


def _eval_item(title: str, label: int) -> EvalItem:
    return EvalItem(
        source="test",
        external_id=title,
        title=title,
        url="",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        summary=None,
        label=label,
    )


def test_scripted_fake_llm_maps_prompt_to_response() -> None:
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8", "beta": "2"})

    assert llm.complete("texte alpha ici") == "8"
    assert llm.complete("texte beta ici") == "2"


def test_scripted_fake_llm_falls_back_to_canned() -> None:
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8"})

    assert llm.complete("aucune correspondance") == "0"


def test_evaluate_produces_consistent_report() -> None:
    dataset = [_eval_item("alpha", 8), _eval_item("beta", 2)]
    # build_prompt insère le titre dans le prompt : on mappe donc sur le titre.
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8", "beta": "2"})

    report = evaluate(dataset, make_llm_scorer(llm))

    assert report.predictions == [8, 2]
    assert report.labels == [8, 2]
    assert report.metric_value == pytest.approx(1.0)


def test_evaluate_maps_malformed_output_to_neutral_score() -> None:
    # coherence avec le module 1.3 : sortie non parsable -> score neutre 0
    dataset = [_eval_item("gamma", 5)]
    llm = ScriptedFakeLLM(canned="pas un nombre")

    report = evaluate(dataset, make_llm_scorer(llm))

    assert report.predictions == [0]
    assert report.labels == [5]


def test_report_is_pydantic_and_serialisable() -> None:
    report = Report(predictions=[6, 4], labels=[7, 4], metric_value=0.9)

    assert isinstance(report, BaseModel)
    assert len(report.predictions) == len(report.labels)

    restored = Report.model_validate_json(report.model_dump_json())
    assert restored == report


def test_dataset_is_valid_ground_truth() -> None:
    dataset = load_dataset()

    assert len(dataset) >= MIN_DATASET_SIZE
    for item in dataset:
        assert isinstance(item, RawItem)
        assert item.title.strip() != ""
        assert MIN_LABEL <= item.label <= MAX_LABEL
        assert "<img" not in item.title
        assert item.summary is None or "<img" not in item.summary
