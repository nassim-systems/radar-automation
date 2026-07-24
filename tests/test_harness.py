from collections.abc import Callable

import pytest
from pydantic import BaseModel

from radar.eval.harness import EvalItem, Report, evaluate, load_dataset
from radar.llm.base import LLMClient
from radar.llm.scripted import ScriptedFakeLLM
from radar.scoring import parse_score

MIN_DATASET_SIZE = 20
MIN_LABEL = 0
MAX_LABEL = 10


def _scorer_from_llm(llm: LLMClient) -> Callable[[str], int]:
    def scorer(text: str) -> int:
        return parse_score(llm.complete(text)).score

    return scorer


def test_scripted_fake_llm_maps_prompt_to_response() -> None:
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8", "beta": "2"})

    assert llm.complete("texte alpha ici") == "8"
    assert llm.complete("texte beta ici") == "2"


def test_scripted_fake_llm_falls_back_to_canned() -> None:
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8"})

    assert llm.complete("aucune correspondance") == "0"


def test_evaluate_produces_consistent_report() -> None:
    dataset = [
        EvalItem(text="alpha", label=8),
        EvalItem(text="beta", label=2),
    ]
    llm = ScriptedFakeLLM(canned="0", mapping={"alpha": "8", "beta": "2"})

    report = evaluate(dataset, _scorer_from_llm(llm))

    assert report.predictions == [8, 2]
    assert report.labels == [8, 2]
    assert report.metric_value == pytest.approx(1.0)


def test_evaluate_maps_malformed_output_to_neutral_score() -> None:
    # coherence avec le module 1.3 : sortie non parsable -> score neutre 0
    dataset = [EvalItem(text="gamma", label=5)]
    llm = ScriptedFakeLLM(canned="pas un nombre")

    report = evaluate(dataset, _scorer_from_llm(llm))

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
        assert item.text.strip() != ""
        assert MIN_LABEL <= item.label <= MAX_LABEL
