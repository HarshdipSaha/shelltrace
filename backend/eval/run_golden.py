"""Execute golden cases through real in-memory MCP and deterministic policy."""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
from collections import defaultdict
from math import ceil
from pathlib import Path
from statistics import mean
from uuid import uuid4
from shelltrace.agent.groq_brain import make_groq_brain
from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.report import TemplateWriter, draft_report
from shelltrace.agent.runner import EXPLORABLE, MANDATORY, run_case
from shelltrace.config import get_settings
from shelltrace.db import GraphStore
from shelltrace.memory.cases import CaseStore, canonical_json
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest
from shelltrace.rulepacks import PACKS
from shelltrace.seed.synthetic import SNAP, load_synthetic
from .ablations import ABLATIONS
from .golden import GOLDEN

OUT = Path(__file__).parent / 'out'


def proposal_agrees(result):
    return result.proposal is not None and result.proposal.disposition == result.disposition


def summarize_latency(steps):
    """Nearest-rank percentiles of observed MCP calls, including policy completion."""
    by_tool = defaultdict(list)
    for step in steps:
        if step.kind == 'tool' and step.tool and step.latency_ms is not None:
            by_tool[step.tool].append(step.latency_ms)
    summary = {}
    for tool, values in sorted(by_tool.items()):
        values.sort()
        n = len(values)
        summary[tool] = dict(p50_ms=values[ceil(n * .5) - 1],
                             p95_ms=values[ceil(n * .95) - 1], n=n)
    return summary


class _Meter:
    def __init__(self, brain):
        self.brain, self.model_id, self.calls = brain, brain.model_id, 0

    async def next_action(self, *args):
        self.calls += 1
        return await self.brain.next_action(*args)

    async def propose(self, *args):
        self.calls += 1
        return await self.brain.propose(*args)

    def observe(self, *args):
        return self.brain.observe(*args)


async def grade(gc, result, cases, req, settings):
    errors = []
    if result.disposition != gc.expect_disposition:
        errors.append(f'disposition: {result.disposition} != {gc.expect_disposition}')
    for name, verdict in gc.expect_verdicts.items():
        if name not in result.packs or result.packs[name].verdict != verdict:
            errors.append(f'verdict: {name} != {verdict}')
    ofac = result.packs.get('OFAC')
    if gc.expect_proof is not None and (ofac is None or not gc.expect_proof <= set(ofac.proof)):
        errors.append('OFAC proof subset mismatch')
    if gc.expect_decisive is not None and (ofac is None or gc.expect_decisive != set(ofac.decisive)):
        errors.append('OFAC decisive mismatch')
    if any(key not in result.evidence for pack in result.packs.values() for key in pack.proof):
        errors.append('unresolved proof')
    report = await draft_report(result, TemplateWriter())
    unsupported = sum(s.kind == 'claim' and not s.supported for s in report.sentences)
    if unsupported:
        errors.append(f'unsupported report claims: {unsupported}')
    tools = [s for s in result.steps if s.kind == 'tool']
    fingerprints = [(s.tool, canonical_json(s.args)) for s in tools]
    if len(set(fingerprints)) != len(fingerprints):
        errors.append('duplicate tool and args')
    if any(s.tool not in EXPLORABLE for s in tools):
        errors.append('forbidden tool')
    explore = [s for s in tools if s.actor not in {'policy', 'playbook'}]
    if len(explore) > settings.budget_steps:
        errors.append('explore step budget exceeded')
    keys = {k for p in result.packs.values() for k in (*p.proof, *p.decisive, *p.presumptions)}
    keys.update(k for f in result.red_flags for k in f.evidence_keys)
    if result.trace:
        keys.update(e.k for e in result.trace.edges)
        keys.add(result.trace.designation_key)
    budget = settings.budget_steps + len(MANDATORY(req)) + 1 + (len(keys) + 19) // 20
    if len(tools) > budget:
        errors.append('total tool budget exceeded')
    if not cases.verify_chain(result.case_id):
        errors.append('invalid audit chain')
    return dict(id=gc.id, category=gc.category, expected=gc.expect_disposition, actual=result.disposition,
                correct=not errors, errors=errors, disposition=result.disposition,
                verdicts={p: r.verdict for p, r in result.packs.items()}, unsupported_claims=unsupported,
                steps=len(result.steps), explore_steps=len(explore), latency_ms=result.latency_ms,
                proposal_agreement=proposal_agrees(result))


def _markdown(report):
    lines = ['# ShellTrace golden evaluation', '', f"Playbook: {report['playbook']['correct']}/{report['total']}", '']
    for category in sorted({g.category for g in GOLDEN}):
        lines += [f'## {category}', '', '| Case | Correct | Disposition | Errors |', '| --- | --- | --- | --- |']
        for gc in GOLDEN:
            if gc.category == category:
                r = report['cases'][gc.id]
                lines.append(f"| {gc.id} | {r['correct']} | {r['disposition']} | {'; '.join(r['errors'])} |")
        lines.append('')
    lines += ['## Ablations', '', '| Method | Correct |', '| --- | --- |']
    lines += [f"| {name} | " + (f"{r['correct']}/{r['total']}" if r.get('available', True) else 'unavailable') + ' |'
              for name, r in report['ablations'].items()]
    lines += ['', 'Ablations score disposition agreement, including coincidental clear cases. Time-off retains the same dated evidence authoriser.', '']
    lines += ['## Tool latency', '', '| Tool | p50 (ms) | p95 (ms) | Calls |', '| --- | --- | --- | --- |']
    lines += [f"| {tool} | {m['p50_ms']} | {m['p95_ms']} | {m['n']} |" for tool, m in report['latency'].items()]
    lines.append('')
    if 'agent' in report:
        lines += [f"## Agent ({report['agent']['repeats']} repeats)", '', '| Metric | Value |', '| --- | --- |']
        lines += [f'| {k} | {v} |' for k, v in report['agent'].items() if k != 'cases']
    return '\n'.join(lines) + '\n'


async def run(mode='playbook', repeats=1, ablations=True, *, store=None, settings=None, output_dir=OUT, brain_factory=None):
    if mode not in {'playbook', 'agent'} or repeats < 1:
        raise ValueError('Use playbook or agent mode and positive repeats')
    settings = settings or get_settings()
    store = store or GraphStore(settings)
    if not store.ping():
        raise RuntimeError('FalkorDB is not reachable')
    brain_factory = brain_factory or make_groq_brain
    if mode == 'agent' and brain_factory is make_groq_brain and not settings.groq_keys:
        raise ValueError('Agent evaluation requires a Groq key')
    ws = 'eval_' + uuid4().hex[:16]
    noer = ws + '_noer'
    report = dict(total=len(GOLDEN), snapshot=SNAP, cases={}, ablations={},
                  snapshot_versions={'synthetic': SNAP, 'rulepacks': {name: pack.version for name, pack in PACKS.items()}})
    observed_steps = []
    created = []
    try:
        created.append(ws)
        store.provision(ws, load_synthetic, force_seed=True)
        if ablations:
            created.append(noer)
            store.provision(noer, lambda g: load_synthetic(g, accept_aliases=False), force_seed=True)
        cases = CaseStore(store.workspace(ws))
        async with McpMemoryToolPort(build_mcp(store)) as port:
            for gc in GOLDEN:
                req = CaseRequest(workspace=ws, entity_id=gc.entity_id, as_of=gc.as_of, rulepacks=list(gc.packs), mode='playbook')
                result = await run_case(req, port, cases, None, settings, SNAP)
                observed_steps.extend(result.steps)
                report['cases'][gc.id] = await grade(gc, result, cases, req, settings)
            report['playbook'] = dict(correct=sum(r['correct'] for r in report['cases'].values()), total=len(GOLDEN))
            if mode == 'agent':
                samples = {}
                for gc in GOLDEN:
                    samples[gc.id] = []
                    for _ in range(repeats):
                        # Independent trials cannot recall baseline or earlier golden labels.
                        trial_ws = 'eval_' + uuid4().hex[:16]
                        try:
                            store.provision(trial_ws, load_synthetic, force_seed=True)
                            trial_cases = CaseStore(store.workspace(trial_ws))
                            req = CaseRequest(workspace=trial_ws, entity_id=gc.entity_id, as_of=gc.as_of, rulepacks=list(gc.packs), mode='agent')
                            brain = _Meter(brain_factory(settings))
                            result = await run_case(req, port, trial_cases, brain, settings, SNAP)
                            observed_steps.extend(result.steps)
                            row = await grade(gc, result, trial_cases, req, settings)
                            row.update(model_calls=brain.calls, disposition_correct=result.disposition == gc.expect_disposition)
                            samples[gc.id].append(row)
                        finally:
                            store.drop(trial_ws)
                rows = [r for group in samples.values() for r in group]
                report['agent'] = dict(repeats=repeats, cases=samples,
                    disposition_only_pass_all=mean(all(r['disposition_correct'] for r in group) for group in samples.values()),
                    disposition_pass_all=mean(all(r['correct'] for r in group) for group in samples.values()),
                    validated_pass_all=mean(all(r['correct'] for r in group) for group in samples.values()),
                    proposal_agreement_pass_all=mean(all(r['proposal_agreement'] for r in group) for group in samples.values()),
                    mean_explore_steps=mean(r['explore_steps'] for r in rows),
                    mean_model_calls=mean(r['model_calls'] for r in rows), mean_latency_ms=mean(r['latency_ms'] for r in rows))
                if repeats == 5:
                    report['agent']['disposition_pass5'] = report['agent']['disposition_only_pass_all']
                    report['agent']['proposal_agreement_pass5'] = report['agent']['proposal_agreement_pass_all']
        if ablations:
            for name, method in ABLATIONS.items():
                graph = store.workspace(noer if name == 'er_off' else ws)
                rows = {}
                for gc in GOLDEN:
                    disposition = method(graph, gc)
                    rows[gc.id] = dict(disposition=disposition, correct=disposition == gc.expect_disposition)
                report['ablations'][name] = dict(correct=sum(r['correct'] for r in rows.values()), total=len(GOLDEN), cases=rows)
        report['ablations']['playbook'] = dict(available=True, **report['playbook'])
        if 'agent' in report:
            report['ablations']['agent'] = dict(available=True, total=len(GOLDEN),
                correct=sum(all(r['disposition_correct'] for r in group) for group in samples.values()))
        else:
            report['ablations']['agent'] = dict(available=False, correct=None, total=len(GOLDEN), reason='not_run')
        report['latency'] = summarize_latency(observed_steps)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / 'golden_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        (output_dir / 'golden_report.md').write_text(_markdown(report), encoding='utf-8')
        return report
    finally:
        for workspace in reversed(created):
            store.drop(workspace)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', action='store_true')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--gate', action='store_true')
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    logging.basicConfig(level=logging.WARNING)
    report = asyncio.run(run('agent' if args.agent else 'playbook', args.repeats))
    print(f"playbook {report['playbook']['correct']}/{report['total']}")
    for name, row in report['ablations'].items():
        print(f"{name}: " + (f"{row['correct']}/{row['total']}" if row.get('available', True) else 'unavailable'))
    if 'agent' in report:
        print(json.dumps({k: v for k, v in report['agent'].items() if k != 'cases'}, indent=2))
    return int(args.gate and report['playbook']['correct'] != len(GOLDEN))


if __name__ == '__main__':
    raise SystemExit(main())
