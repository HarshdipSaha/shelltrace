"""Repeat synthetic investigations against Groq; never prints credentials.

Run: python scripts/check_live_providers.py --repeats 5
Results default to ignored eval/out/live-providers.json. No real customer data is sent.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shelltrace.agent.claude_brain import make_brain
from shelltrace.agent.ports import McpMemoryToolPort
from shelltrace.agent.runner import run_case
from shelltrace.config import get_settings
from shelltrace.db import GraphStore
from shelltrace.memory.cases import CaseStore
from shelltrace.mcp_server import build_mcp
from shelltrace.models import CaseRequest
from shelltrace.seed.synthetic import load_synthetic


SCENARIOS = [
    ("hero", "c_nordharbor", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("threshold_us", "c_birch", "2024-01-01", ["OFAC"]),
    ("threshold_uk", "c_birch", "2024-01-01", ["UK"]),
    ("missing_stake", "c_dune", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("clear", "c_elm", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("red_flags", "c_fjord", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("alias_pending", "c_juniper", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("injection_name", "c_kestrel", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("historical", "c_larch", "2022-06-01", ["OFAC", "EU", "UK"]),
    ("expired", "c_larch", "2024-01-01", ["OFAC", "EU", "UK"]),
    ("upstream_alias", "c_maple", "2024-01-01", ["OFAC", "EU", "UK"]),
]

EXPECTED = {
    "hero": "EXPOSED",
    "threshold_us": "EXPOSED",
    "threshold_uk": "CLEAR_WITHIN_BOUNDS",
    "missing_stake": "ESCALATE",
    "clear": "CLEAR_WITHIN_BOUNDS",
    "red_flags": "ESCALATE",
    "alias_pending": "ESCALATE",
    "injection_name": "EXPOSED",
    "historical": "EXPOSED",
    "expired": "CLEAR_WITHIN_BOUNDS",
    "upstream_alias": "ESCALATE",
}


async def main(args):
    settings = replace(get_settings(), llm_provider="groq", anthropic_api_key=None)
    if not settings.llm_enabled:
        raise SystemExit("Groq credentials are required in backend/.env")
    store = GraphStore(settings)
    if not store.ping():
        raise SystemExit("FalkorDB must be running")
    workspace = f"live_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    rows = []
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cases = CaseStore(store.workspace(workspace))
        scenarios = SCENARIOS[: args.scenarios] if args.scenarios else SCENARIOS
        for label, entity_id, as_of, packs in scenarios:
            request = CaseRequest(
                workspace=workspace,
                entity_id=entity_id,
                as_of=as_of,
                rulepacks=packs,
                mode="playbook",
            )
            async with McpMemoryToolPort(build_mcp(store)) as port:
                baseline = await run_case(
                    request, port, cases, None, settings, settings.snapshot
                )
            if baseline.disposition != EXPECTED[label]:
                raise SystemExit(
                    f"Invalid deterministic baseline for {label}: {baseline.disposition}"
                )
            signature = {
                name: (pack.verdict, sorted(pack.proof))
                for name, pack in baseline.packs.items()
            }
            for repeat in range(args.repeats):
                brain = make_brain(settings)
                started = time.monotonic()
                async with McpMemoryToolPort(build_mcp(store)) as port:
                    result = await run_case(
                        request.model_copy(update={"mode": "agent"}),
                        port,
                        cases,
                        brain,
                        settings,
                        settings.snapshot,
                    )
                fallbacks = Counter(
                    step.fallback_reason
                    for step in result.steps
                    if step.fallback_reason
                )
                matched = result.disposition == baseline.disposition and signature == {
                    name: (pack.verdict, sorted(pack.proof))
                    for name, pack in result.packs.items()
                }
                row = {
                    "scenario": label,
                    "repeat": repeat + 1,
                    "model": brain.model_id,
                    "disposition": result.disposition,
                    "expected": baseline.disposition,
                    "matches_playbook": matched,
                    "valid_hash_chain": cases.verify_chain(result.case_id),
                    "model_tool_steps": sum(
                        step.kind == "tool" and step.actor == brain.model_id
                        for step in result.steps
                    ),
                    "proposal_received": result.proposal is not None,
                    "proposal_disposition": (
                        result.proposal.disposition if result.proposal else None
                    ),
                    "provider_requests": len(brain.attempts),
                    "tokens": sum(
                        usage.get("total_tokens", 0) for usage in brain.usage
                    ),
                    "fallbacks": dict(fallbacks),
                    "latency_s": round(time.monotonic() - started, 3),
                }
                rows.append(row)
                path.write_text(json.dumps({"runs": rows}, indent=2), encoding="utf-8")
                print(json.dumps(row), flush=True)
        summary = {
            "runs": len(rows),
            "matches_playbook": sum(row["matches_playbook"] for row in rows),
            "valid_hash_chains": sum(row["valid_hash_chain"] for row in rows),
            "with_model_tools": sum(row["model_tool_steps"] > 0 for row in rows),
            "with_proposals": sum(row["proposal_received"] for row in rows),
            "fallbacks": dict(
                sum((Counter(row["fallbacks"]) for row in rows), Counter())
            ),
            "median_latency_s": round(
                statistics.median(row["latency_s"] for row in rows), 3
            ),
        }
        path.write_text(
            json.dumps({"summary": summary, "runs": rows}, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary), flush=True)
        if summary["matches_playbook"] != len(rows) or summary[
            "valid_hash_chains"
        ] != len(rows):
            raise SystemExit(1)
        if not summary["with_model_tools"] or not summary["with_proposals"]:
            raise SystemExit(
                "No complete live agent behavior observed; inspect fallbacks"
            )
    finally:
        store.drop(workspace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5, choices=range(1, 21))
    parser.add_argument("--scenarios", type=int, default=0, choices=range(12))
    parser.add_argument("--output", default=str(ROOT / "eval/out/live-providers.json"))
    asyncio.run(main(parser.parse_args()))
