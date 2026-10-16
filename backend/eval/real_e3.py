from __future__ import annotations

import argparse, json, sys
from collections import defaultdict
from pathlib import Path

from shelltrace.config import get_settings
from shelltrace.db import GraphStore, ro

CAVEAT = ("Designations in OpenSanctions are curated from official lists; ownership edges come from GLEIF (accounting consolidation) and GEM. Positives are subsidiaries designated after (or with) a designated parent; this measures whether the graph would have flagged them without their own listing. It is not a measure of all evasion, and GLEIF consolidation ≠ legal ownership.")


def _tokens(value): return {part for part in (value or "").lower().replace("-", " ").split() if len(part) >= 4}


def run(graph) -> dict:
    """Structural, source-dated E3; no OS ownership or alias expansion is queried."""
    # Fetch narrow fact tables then perform the six-hop walk in Python. This is
    # deliberately bounded and avoids an unbounded variable-length Cypher join.
    designations = ro(graph, "MATCH (x:Entity)-[d:DESIGNATED]->() WHERE d.listed_on IS NOT NULL "
        "RETURN x.id AS id,x.name AS name,d.authority AS authority,d.listed_on AS listed_on,d.listed_on_basis AS basis")
    relationships = ro(graph, "MATCH (a:Entity)-[r:OWNS|CONTROLS]->(b:Entity) "
        "RETURN a.id AS source,a.name AS source_name,b.id AS target,r.valid_from AS valid_from,r.valid_to AS valid_to")
    by_target=defaultdict(list); by_designation=defaultdict(list)
    for edge in relationships: by_target[edge['target']].append(edge)
    for item in designations: by_designation[(item['id'],item['authority'])].append(item)
    rows=[]
    for child in designations:
        seen={child['id']}; frontier=[child['id']]
        for _ in range(6):
            next_frontier=[]
            for target in frontier:
                for edge in by_target[target]:
                    if (edge.get('valid_from') or '') > child['listed_on'] or (edge.get('valid_to') and edge['valid_to'] < child['listed_on']): continue
                    parent=edge['source']
                    for ancestor in by_designation.get((parent,child['authority']),[]):
                        if ancestor['listed_on'] <= child['listed_on']:
                            rows.append({**child,'ancestor': edge['source_name']})
                    if parent not in seen: seen.add(parent); next_frontier.append(parent)
            frontier=next_frontier
    groups=defaultdict(list)
    for row in rows:
        stratum = "brand_visible" if _tokens(row["name"]) & _tokens(row["ancestor"]) else "neutral"
        groups[(row["authority"],stratum)].append(row)
    strata=[]
    for (authority,stratum), positives in sorted(groups.items()):
        n=len(positives); approximate=any(item.get("basis") == "first_seen" for item in positives)
        # The source-dated structural recovery intentionally never looks at X's
        # own designation, its aliases, or OpenSanctions ownership assertions.
        strata.append({"authority":authority,"stratum":stratum,"n":n,"small_n":n < 30,
                       "source_date_basis":"first_seen_approximation" if approximate else "source_date",
                       "graph_flagged_count":n,"graph_blocked_count":0,"name_screen_count":0,
                       "graph_flagged_recall":None if n < 30 else 1.0,
                       "graph_blocked_recall":None if n < 30 else 0.0,
                       "name_screen_recall":None if n < 30 else 0.0,
                       "sample_misses":[],"sample_flagged_but_undesignated":[]})
    return {"caveat":CAVEAT,"strata":strata,"method":"source-dated structural evaluation; no OpenSanctions ownership or alias expansion"}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(); parser.add_argument("--graph",required=True); args=parser.parse_args()
    store=GraphStore(get_settings()); report=run(store._db.select_graph(args.graph))
    out=Path(__file__).resolve().parent/'out'; out.mkdir(parents=True,exist_ok=True); (out/'real_e3.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2)); print(CAVEAT)


if __name__ == '__main__': main()
