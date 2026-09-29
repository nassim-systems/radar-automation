"""Hardening of the ``measured`` flag (Phase 5.1): ``measured=True`` must never
come out of ``scripts/measure_human_baseline.py`` without an explicit and
exact confirmation from the operator.

Load the script as a module (``importlib``; ``scripts/`` is not an installed
package) to test ``_is_measured_confirmed`` in isolation, without mocking
``input`` or running the whole interactive flow of ``main()``.
"""
import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "measure_human_baseline.py"
)


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "measure_human_baseline", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_is_measured_confirmed_true_on_exact_yes() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("yes") is True


def test_is_measured_confirmed_is_case_and_whitespace_tolerant() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("Yes") is True
    assert module._is_measured_confirmed("YES") is True
    assert module._is_measured_confirmed("  yes  ") is True


def test_is_measured_confirmed_false_on_no() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("no") is False


def test_is_measured_confirmed_false_on_empty_response() -> None:
    # Enter pressed without thinking: never measured=True by default.
    module = _load_script_module()

    assert module._is_measured_confirmed("") is False
    assert module._is_measured_confirmed("   ") is False


def test_is_measured_confirmed_false_on_anything_not_exactly_yes() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("yes, really") is False
    assert module._is_measured_confirmed("yes.") is False
    assert module._is_measured_confirmed("yeah") is False
    assert module._is_measured_confirmed("y") is False


def test_default_out_points_to_human_baseline_json() -> None:
    # human_baseline.json was removed from the repo (local data, never
    # committed); this test only pins the file name the script
    # produces, not the presence of the file itself.
    module = _load_script_module()

    assert module.DEFAULT_OUT.name == "human_baseline.json"
