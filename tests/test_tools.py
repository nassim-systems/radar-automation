import pytest
from pydantic import ValidationError

from agent.agent import actions_gate
from agent.agent.actions_gate import gate_action
from agent.tools import actions, registry
from agent.tools.actions import propose_send_email
from agent.tools.base import ProposedAction
from agent.tools.read import CrmReadTool, KnowledgeBaseReadTool
from agent.tools.registry import ReadToolRegistry


def test_read_tool_is_read_only_without_llm() -> None:
    tool = CrmReadTool({"a@b.fr": "Client ACME — offre Pro"})

    hit = tool.read("a@b.fr")
    assert hit.ok
    assert "ACME" in hit.data

    miss = tool.read("inconnu@x.fr")
    assert not miss.ok
    assert miss.data == ""


def test_registry_structured_read_selection() -> None:
    reg = ReadToolRegistry(
        [
            CrmReadTool({"a@b.fr": "ACME"}),
            KnowledgeBaseReadTool({"retour": "Retours acceptés sous 30 jours"}),
        ]
    )

    assert reg.names() == ["crm_lookup", "kb_search"]
    assert reg.read("crm_lookup", "a@b.fr").data == "ACME"
    assert reg.read("kb_search", "RETOUR").ok
    # unknown tool -> clean failure, no exception
    assert not reg.read("inexistant", "x").ok


def test_proposed_action_requires_human_approval_is_structural() -> None:
    # even when forcing False, the invariant holds (validation)
    action = ProposedAction(
        action="send_email",
        params={"to": "a@b.fr"},
        reason="test",
        requires_human_approval=False,
    )
    assert action.requires_human_approval is True

    # frozen model: cannot be set back to False afterwards
    with pytest.raises(ValidationError):
        action.requires_human_approval = False


def test_no_autonomous_execution_path_for_actions() -> None:
    action = propose_send_email(
        to="a@b.fr", subject="Bonjour", body="...", reason="réponse client"
    )

    # 1. the action is inert data: nothing to execute it
    assert isinstance(action, ProposedAction)
    assert action.requires_human_approval is True
    assert not callable(action)
    for attr in ("execute", "run", "perform", "send", "apply", "dispatch"):
        assert not hasattr(action, attr)

    # 2. an action is not a read tool: cannot enter the registry
    assert not hasattr(action, "read")

    # 3. the action gate only waits for the human, never executes
    decision = gate_action(action)
    assert decision.approved is False
    assert decision.status == "pending_human_approval"

    # 4. no module in the system exposes an action-execution primitive
    forbidden = {"execute", "run_action", "perform", "dispatch", "apply"}
    for module in (actions, registry, actions_gate):
        exported = {name for name in dir(module) if not name.startswith("_")}
        assert not (exported & forbidden)
