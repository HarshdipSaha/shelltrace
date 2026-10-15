import os
from dataclasses import replace
from uuid import uuid4

import pytest

from shelltrace.agent.claude_brain import make_brain
from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.runner import run_case
from shelltrace.config import get_settings
from shelltrace.memory.cases import CaseStore
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest
from shelltrace.seed.synthetic import load_synthetic

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="requires a billable Anthropic API key",
)


@pytest.mark.asyncio
async def test_claude_case_uses_tools_and_prompt_cache(store):
    settings = replace(
        get_settings(),
        llm_provider="anthropic",
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    workspace = f"live_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    try:
        req = CaseRequest(
            workspace=workspace,
            entity_id="c_juniper",
            as_of="2024-01-01",
            max_hops=6,
            rulepacks=["OFAC", "EU", "UK"],
            mode="agent",
        )
        brain = make_brain(settings)
        assert brain is not None
        async with McpMemoryToolPort(build_mcp(store)) as port:
            result = await run_case(
                req,
                port,
                CaseStore(store.workspace(workspace)),
                brain,
                settings,
                settings.snapshot,
            )

        assert result.disposition == "ESCALATE"
        assert any(step.actor == brain.model_id for step in result.steps)
        assert len(brain.usage) > 1
        assert brain.usage[1].cache_read_input_tokens > 0
    finally:
        store.drop(workspace)
