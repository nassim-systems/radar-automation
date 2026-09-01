"""Durcissement du flag ``measured`` (Phase 5.1) : ``measured=True`` ne doit
jamais pouvoir sortir de ``scripts/measure_human_baseline.py`` sans une
confirmation explicite et exacte de l'opérateur.

Charge le script comme un module (``importlib`` — ``scripts/`` n'est pas un
package installé) pour tester ``_is_measured_confirmed`` en isolation, sans
mocker ``input`` ni dérouler tout le flux interactif de ``main()``.
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


def test_is_measured_confirmed_true_on_exact_oui() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("oui") is True


def test_is_measured_confirmed_is_case_and_whitespace_tolerant() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("Oui") is True
    assert module._is_measured_confirmed("OUI") is True
    assert module._is_measured_confirmed("  oui  ") is True


def test_is_measured_confirmed_false_on_non() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("non") is False


def test_is_measured_confirmed_false_on_empty_response() -> None:
    # Entrée pressée sans réfléchir : jamais measured=True par défaut.
    module = _load_script_module()

    assert module._is_measured_confirmed("") is False
    assert module._is_measured_confirmed("   ") is False


def test_is_measured_confirmed_false_on_anything_not_exactly_oui() -> None:
    module = _load_script_module()

    assert module._is_measured_confirmed("oui, vraiment") is False
    assert module._is_measured_confirmed("yes") is False
    assert module._is_measured_confirmed("ouais") is False
    assert module._is_measured_confirmed("o") is False


def test_default_out_points_to_human_baseline_json() -> None:
    # human_baseline.json a été supprimé du dépôt (donnée locale, jamais
    # commitée) ; ce test fige seulement le nom de fichier que le script
    # produit, pas la présence du fichier lui-même.
    module = _load_script_module()

    assert module.DEFAULT_OUT.name == "human_baseline.json"
