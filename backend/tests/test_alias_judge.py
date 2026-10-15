import json
import httpx
import pytest

from shelltrace.graph.alias_judge import JevAliasJudge


async def test_jev_choice_uses_stored_identifiers_and_returns_distribution():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "jev-release",
                "answers": {
                    "identity": {
                        "type": "choice",
                        "choice": "same_entity",
                        "confidence": 0.9,
                        "probabilities": {
                            "same_entity": 0.9,
                            "different_entity": 0.05,
                            "uncertain": 0.05,
                        },
                    }
                },
            },
        )

    result = await JevAliasJudge("key", transport=httpx.MockTransport(handler)).judge(
        {"id": "a", "name": "Nord Harbor"}, {"id": "b", "name": "Nord Harbour"}
    )
    assert result.recommendation == "same_entity"
    assert result.model == "jev-release"
    assert result.probabilities["same_entity"] == 0.9
    assert calls[0]["questions"]["identity"]["type"] == "choice"
    assert calls[0]["state"]["a"]["id"] == "a"


@pytest.mark.parametrize(
    "a,b",
    [
        ({"lei": "x"}, {"lei": "y"}),
        ({"imo": "x"}, {"imo": "y"}),
        ({"country": "GB", "reg_no": "x"}, {"country": "GB", "reg_no": "y"}),
    ],
)
async def test_identifier_conflicts_never_reach_network(a, b):
    def handler(_):
        pytest.fail("identifier conflict must not invoke JEV")

    result = await JevAliasJudge("key", transport=httpx.MockTransport(handler)).judge(
        a, b
    )
    assert result.recommendation == "different_entity"
    assert result.source == "deterministic"
    assert result.reason.startswith("identifier_conflict:")


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {
            "type": "choice",
            "choice": "same_entity",
            "confidence": 0.9,
            "probabilities": {"same_entity": 0.9},
        },
        {
            "type": "choice",
            "choice": "same_entity",
            "confidence": 0.9,
            "probabilities": {"same_entity": -1, "different_entity": 1, "uncertain": 1},
        },
    ],
)
async def test_jev_malformed_distribution_abstains(answer):
    result = await JevAliasJudge(
        "key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"model": "jev", "answers": {"identity": answer}}
            )
        ),
    ).judge({}, {})
    assert result.recommendation == "uncertain"
    assert result.reason == "invalid_response"


async def test_jev_outage_and_disabled_abstain():
    judge = JevAliasJudge(
        "key", transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    assert (await judge.judge({}, {})).reason == "api_503"
    assert (await JevAliasJudge(None).judge({}, {})).reason == "disabled"


async def test_jev_low_confidence_abstains_with_distribution():
    answer = {
        "type": "choice",
        "choice": "same_entity",
        "confidence": 0.5,
        "probabilities": {
            "same_entity": 0.9,
            "different_entity": 0.05,
            "uncertain": 0.05,
        },
    }
    result = await JevAliasJudge(
        "key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"model": "jev", "answers": {"identity": answer}}
            )
        ),
    ).judge({}, {})
    assert result.recommendation == "uncertain"
    assert result.confidence == 0.5
    assert result.source == "jev"


async def test_jev_transport_timeout_abstains():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    result = await JevAliasJudge("key", transport=httpx.MockTransport(handler)).judge(
        {}, {}
    )
    assert result.recommendation == "uncertain"
    assert result.reason == "timeout_or_connection"
