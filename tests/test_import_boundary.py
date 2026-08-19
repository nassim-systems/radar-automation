"""Frontière d'import : le package ``agent`` ne peut agir sur le monde.

Mécanisme choisi : un test qui parse l'AST de chaque module de ``src/agent`` et
vérifie qu'aucun ``import`` ne cible ``executor`` ni un client sortant (SMTP,
requests, urllib/http, socket…).

Justification (AST-grep plutôt qu'import-linter) :
- Zéro dépendance nouvelle et zéro fichier de config : la garantie vit dans la
  suite pytest déjà exécutée par ``check.sh`` (invariant testé en continu).
- Parse réel (pas un grep textuel) : ignore les imports en commentaires ou
  chaînes, ne relève que de vrais ``import``/``from ... import``.
- Cible précisément le bon périmètre : les imports DIRECTS du code de ``agent``.
  C'est exactement la frontière voulue — l'agent ne doit pas, dans son propre
  code, tenir la capacité d'agir. La séparation en packages (``executor`` à part)
  rend l'infraction visible et testable.
"""
import ast
from pathlib import Path

FORBIDDEN = {
    "executor",
    "smtplib",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "http",
    "socket",
    "ftplib",
}

AGENT_DIR = Path(__file__).resolve().parents[1] / "src" / "agent"


def _imported_top_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return {module.split(".")[0] for module in modules}


def test_agent_dir_exists() -> None:
    # garde-fou : si le chemin est faux, le test ci-dessous serait vide et faux
    assert AGENT_DIR.is_dir()


def test_agent_does_not_import_executor_or_outgoing_clients() -> None:
    offenders: list[str] = []
    for path in sorted(AGENT_DIR.rglob("*.py")):
        forbidden_here = _imported_top_modules(path) & FORBIDDEN
        offenders += [f"{path.name}: {module}" for module in sorted(forbidden_here)]

    assert offenders == [], f"imports interdits dans agent/ : {offenders}"
