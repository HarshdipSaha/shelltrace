import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.runner import run_case
from shelltrace.config import get_settings
from shelltrace.memory.cases import CaseStore
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest
from shelltrace.seed.synthetic import load_synthetic


@pytest.fixture(scope="module")
def case_hero(store):
    workspace = f"rp_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    try:
        request = CaseRequest(
            workspace=workspace,
            entity_id="c_nordharbor",
            as_of="2024-01-01",
            max_hops=6,
            rulepacks=["OFAC", "EU", "UK"],
            mode="playbook",
        )
        cases = CaseStore(store.workspace(workspace))

        async def run():
            async with McpMemoryToolPort(build_mcp(store)) as port:
                return await run_case(
                    request,
                    port,
                    cases,
                    None,
                    get_settings(),
                    get_settings().snapshot,
                )

        result = asyncio.run(run())
        yield result
    finally:
        store.drop(workspace)


class FakeMessages:
    def __init__(self, content):
        self.content = content
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self.content)


def fake_client_citing(citations_and_text):
    blocks = [
        SimpleNamespace(
            type="text",
            text=text,
            citations=[SimpleNamespace(document_index=index)],
        )
        for index, text in citations_and_text
    ]
    messages = FakeMessages(blocks)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def test_template_report_is_fully_supported(case_hero):
    from shelltrace.agent.report import TemplateWriter, draft_report

    report = asyncio.run(draft_report(case_hero, TemplateWriter()))
    claims = [sentence for sentence in report.sentences if sentence.kind == "claim"]

    assert claims and all(sentence.supported for sentence in claims)
    assert "not legal advice" in report.markdown.lower()


def test_uncited_claim_is_struck(case_hero):
    from shelltrace.agent.report import ReportSentence, verify_sentences

    out = verify_sentences(
        [ReportSentence("Volkov controls the target.", [], "claim")], case_hero
    )

    assert (out[0].supported, out[0].problem) == (False, "no_citation")


def test_citation_outside_validated_evidence_is_struck(case_hero):
    from shelltrace.agent.report import ReportSentence, verify_sentences

    out = verify_sentences(
        [ReportSentence("Meridian owns Blue Lagoon.", ["syn:G5-1"], "claim")],
        case_hero,
    )

    assert out[0].problem == "citation_outside_validated_evidence"


def test_wrong_entity_citation_is_struck(case_hero):
    from shelltrace.agent.report import ReportSentence, verify_sentences

    out = verify_sentences(
        [
            ReportSentence(
                "Nord Harbor Logistics Ltd is owned 100% by Arkady Volkov.",
                ["syn:G1-1"],
                "claim",
            )
        ],
        case_hero,
    )

    assert out[0].problem == "wrong_entity_citation"


@pytest.mark.asyncio
async def test_claude_writer_maps_citations_to_keys(case_hero):
    from shelltrace.agent.report import ClaudeWriter, draft_report, ordered_evidence_keys

    client = fake_client_citing(
        [(0, "Arkady Volkov owns 100% of Meridian Holdings SA.")]
    )
    report = await draft_report(
        case_hero,
        ClaudeWriter("claude-opus-5", client),
    )

    assert report.sentences[0].keys == [ordered_evidence_keys(case_hero)[0]]
    request = client.beta.messages.calls[0]
    assert request["model"] == "claude-opus-5"
    assert "output_config" not in request
    assert [
        document["title"]
        for document in request["messages"][0]["content"]
        if document.get("type") == "document"
    ] == ordered_evidence_keys(case_hero)
