from shelltrace.agent.runner import _view
from shelltrace.models import CaseRequest


def test_model_case_context_includes_workspace():
    req = CaseRequest(
        workspace="specific_workspace",
        entity_id="e",
        as_of="2024-01-01",
        rulepacks=["OFAC"],
        mode="agent",
    )
    assert _view(req, 8, 10, [])["case"]["workspace"] == req.workspace
