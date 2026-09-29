"""Import boundary: the ``agent`` package cannot act on the world.

Chosen mechanism: a test that parses the AST of every module in ``src/agent``
and checks that no ``import`` targets ``executor`` or an outbound client (SMTP,
requests, urllib/http, socket…).

Rationale (AST-grep rather than import-linter):
- Zero new dependency and zero config file: the guarantee lives in the pytest
  suite already run by ``check.sh`` (invariant tested continuously).
- Real parse (not a textual grep): ignores imports in comments or strings,
  only picks up real ``import``/``from ... import`` statements.
- Targets exactly the right scope: DIRECT imports in ``agent`` code.
  This is exactly the intended boundary: the agent must not, in its own
  code, hold the ability to act. Splitting into packages (``executor`` apart)
  makes a violation visible and testable.
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
    # guard: if the path is wrong, the test below would be empty and wrong
    assert AGENT_DIR.is_dir()


def test_agent_does_not_import_executor_or_outgoing_clients() -> None:
    offenders: list[str] = []
    for path in sorted(AGENT_DIR.rglob("*.py")):
        forbidden_here = _imported_top_modules(path) & FORBIDDEN
        offenders += [f"{path.name}: {module}" for module in sorted(forbidden_here)]

    assert offenders == [], f"imports interdits dans agent/ : {offenders}"


def test_only_composition_imports_executor() -> None:
    # only the composition module may import executor
    src = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src)
        if rel.parts[0] == "executor" or path.name == "composition.py":
            continue
        if "executor" in _imported_top_modules(path):
            offenders.append(str(rel))

    assert offenders == [], f"executor importé hors composition : {offenders}"
