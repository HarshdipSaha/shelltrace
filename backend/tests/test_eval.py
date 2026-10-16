import pytest


def test_golden_inventory():
    from eval.golden import GOLDEN
    assert len(GOLDEN) == 24
    assert len({case.id for case in GOLDEN}) == 24


async def test_golden_and_ablations(store, tmp_path):
    from eval.run_golden import run
    report = await run(store=store, output_dir=tmp_path)
    assert report['playbook']['correct'] == 24, report['cases']
    ab = report['ablations']
    assert {name: ab[name]['correct'] for name in ('name_only', 'path_only', 'multiplicative', 'er_off', 'time_off')} == {
        'name_only': 7, 'path_only': 14, 'multiplicative': 15, 'er_off': 23, 'time_off': 21
    }
    assert ab['playbook']['correct'] == 24
    assert ab['playbook']['total'] == 24
    assert ab['agent']['available'] is False
    assert ab['agent']['correct'] is None
    assert report['snapshot_versions']['synthetic'] == report['snapshot']
    assert set(report['snapshot_versions']['rulepacks']) == {'OFAC', 'EU', 'UK'}
    assert report['latency']
    for metrics in report['latency'].values():
        assert metrics['n'] > 0
        assert 0 <= metrics['p50_ms'] <= metrics['p95_ms']
    assert ab['multiplicative']['cases']['G3']['correct'] is False
    assert ab['path_only']['cases']['G3uk']['correct'] is False
    assert ab['path_only']['cases']['G5']['correct'] is False
    assert ab['er_off']['cases']['G1']['correct'] is False
    assert ab['time_off']['cases']['G12post']['correct'] is False
    assert ab['time_off']['cases']['G7pre']['correct'] is False
    assert (tmp_path / 'golden_report.json').exists()
    assert (tmp_path / 'golden_report.md').exists()


def test_missing_proposal_is_not_agreement():
    from eval.run_golden import proposal_agrees
    from types import SimpleNamespace
    assert not proposal_agrees(SimpleNamespace(proposal=None, disposition='EXPOSED'))

async def test_agent_repeats_missing_proposals_do_not_pass_agreement(store, tmp_path, monkeypatch):
    from importlib import import_module
    from shelltrace.agent.brain import BrainUnavailable
    runner = import_module('eval.run_golden')
    monkeypatch.setattr(runner, 'GOLDEN', runner.GOLDEN[:1])

    histories = []

    class UnavailableBrain:
        model_id = 'unavailable-test'

        async def next_action(self, *args):
            raise BrainUnavailable('test_unavailable')

        async def propose(self, view):
            import json
            histories.extend(json.loads(item['summary'])['prior_cases']
                             for item in view['evidence_so_far'] if item['tool'] == 'case_history')
            raise BrainUnavailable('test_unavailable')

        def observe(self, *args):
            pass

    report = await runner.run('agent', repeats=5, ablations=False, store=store,
                              output_dir=tmp_path, brain_factory=lambda settings: UnavailableBrain())
    assert report['agent']['disposition_pass_all'] == 1
    assert report['agent']['proposal_agreement_pass_all'] == 0
    assert len(report['agent']['cases']['G1']) == 5
    assert report['agent']['mean_model_calls'] == 2
    assert report['agent']['disposition_pass5'] == report['agent']['disposition_only_pass_all']
    assert report['ablations']['agent']['available'] is True
    assert report['ablations']['agent']['correct'] == 1
    assert report['ablations']['agent']['total'] == 1
    assert histories == [[], [], [], [], []]  # Trials must not reveal prior golden labels.


async def test_grader_rejects_missing_evidence_and_duplicate_tools(store):
    from uuid import uuid4
    from shelltrace.agent.runner import run_case
    from shelltrace.agent.ports import McpMemoryToolPort
    from shelltrace.memory.cases import CaseStore
    from shelltrace.mcp_server import build_mcp
    from shelltrace.seed.synthetic import load_synthetic, SNAP
    from shelltrace.models import CaseRequest
    from shelltrace.config import get_settings
    from eval.golden import GOLDEN
    from eval.run_golden import grade
    ws = 'eg_' + uuid4().hex[:8]
    try:
        store.provision(ws, load_synthetic, force_seed=True)
        cases = CaseStore(store.workspace(ws))
        gc = GOLDEN[0]
        req = CaseRequest(workspace=ws, entity_id=gc.entity_id, as_of=gc.as_of,
                          rulepacks=list(gc.packs), mode='playbook')
        async with McpMemoryToolPort(build_mcp(store)) as port:
            result = await run_case(req, port, cases, None, get_settings(), SNAP)
        result.evidence.pop(result.packs['OFAC'].proof[0])
        result.steps.append(next(step for step in result.steps if step.kind == 'tool'))
        scored = await grade(gc, result, cases, req, get_settings())
        assert not scored['correct']
        assert 'unresolved proof' in scored['errors']
        assert 'duplicate tool and args' in scored['errors']
    finally:
        store.drop(ws)


def test_latency_uses_actual_tool_steps_and_nearest_rank_percentiles():
    from eval.run_golden import summarize_latency
    from types import SimpleNamespace
    steps = [SimpleNamespace(kind='tool', tool='evidence_get', latency_ms=n) for n in range(1, 21)]
    steps.append(SimpleNamespace(kind='proposal', tool=None, latency_ms=10000))
    assert summarize_latency(steps) == {'evidence_get': {'p50_ms': 10, 'p95_ms': 19, 'n': 20}}
