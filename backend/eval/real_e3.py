"""Measure hidden-designation recovery with the production graph tools."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from shelltrace.config import get_settings
from shelltrace.db import GraphStore, ro
from shelltrace.graph.ownership import evaluate
from shelltrace.graph.trace import trace
from shelltrace.rulepacks import get_pack
from shelltrace.screening import screen_name

CAVEAT = ("Designations in OpenSanctions are curated from official lists; ownership edges come from GLEIF (accounting consolidation) and GEM. Positives are subsidiaries designated after (or with) a designated parent; this measures whether the graph would have flagged them without their own listing. It is not a measure of all evasion, and GLEIF consolidation ≠ legal ownership.")
FLAGGED = {'BLOCKED', 'INDETERMINATE', 'PRESUMED_CONTROLLED'}


def read_table(graph, query, page_size=1000):
    """Page below FalkorDB's result-set cap; a bulk query can truncate silently."""
    result, offset = [], 0
    while True:
        page = ro(graph, query + ' SKIP $offset LIMIT $limit', {'offset': offset, 'limit': page_size})
        result.extend(page)
        if len(page) < page_size:
            return result
        offset += page_size


def _tokens(value):
    return {word for word in re.findall(r'\w+', value.casefold()) if len(word) >= 4}


def _active(item, as_of):
    return bool(item.get('listed_on') and item['listed_on'] <= as_of
                and (not item.get('delisted_on') or item['delisted_on'] > as_of))


def _predict(graph, subject, authority, as_of, excluded, members):
    prediction = {'flagged': None, 'blocked': None, 'name_hit': None, 'errors': []}
    try:
        result = evaluate(graph, subject, as_of, get_pack(authority), exclude=tuple(excluded))
        prediction.update(verdict=result.verdict, blocked=result.verdict == 'BLOCKED',
                          flagged=result.verdict in FLAGGED, proof=result.proof)
        if result.scope_truncated:
            prediction['errors'].append('Rule evaluation scope was truncated')
            prediction['blocked'] = None
        if not prediction['flagged']:
            path = trace(graph, subject, as_of, 6, [authority], exclude=tuple(excluded))
            prediction['flagged'] = path is not None
            prediction['trace_designation'] = path.designation_key if path else None
    except Exception as exc:
        if prediction['flagged'] is False:
            prediction['flagged'] = None
        prediction['errors'].append(f'graph: {type(exc).__name__}: {exc}')
    try:
        prediction['name_hit'] = screen_name(graph, subject, [authority], as_of,
                                             exclude_entity_ids=tuple(members),
                                             exclude_designation_keys=tuple(excluded))['hit']
    except Exception as exc:
        prediction['errors'].append(f'name: {type(exc).__name__}: {exc}')
    return prediction


def run(graph, audit_limit=20):
    """Eligibility is distinct from predictions; labels are hidden read-only."""
    if ro(graph, "MATCH ()-[r:OWNS|CONTROLS]->() WHERE r.src STARTS WITH 'opensanctions:' RETURN count(r) AS n")[0]['n']:
        raise ValueError('OpenSanctions ownership/control facts would leak labels into E3')
    entities = read_table(graph, "MATCH (e:Entity) WHERE e.kind IN ['Company','Vessel'] "
                        "RETURN e.id AS id,e.name AS name,coalesce(e.canon,e.id) AS canon ORDER BY id")
    nodes = {row['id']: row for row in entities}
    clusters = defaultdict(list)
    for row in entities:
        clusters[row['canon']].append(row['id'])
    designations = read_table(graph, "MATCH (x:Entity)-[d:DESIGNATED]->(p:Program) "
        "RETURN x.id AS id,d.k AS k,p.authority AS authority,d.listed_on AS listed_on,"
        "d.delisted_on AS delisted_on,d.listed_on_basis AS basis ORDER BY k,id")
    relationships = read_table(graph, "MATCH (a:Entity)-[r:OWNS|CONTROLS]->(b:Entity) "
        "RETURN a.id AS source,b.id AS target,r.k AS k,r.valid_from AS valid_from,r.valid_to AS valid_to ORDER BY k")
    by_target, by_designation = defaultdict(list), defaultdict(list)
    skipped = 0
    for item in designations:
        if item['id'] not in nodes or item['authority'] not in {'OFAC', 'EU', 'UK'}:
            continue
        try:
            date.fromisoformat(item['listed_on'] or '')
        except ValueError:
            skipped += 1
            continue
        by_designation[(nodes[item['id']]['canon'], item['authority'])].append(item)
    for edge in relationships:
        if edge['source'] in nodes and edge['target'] in nodes:
            by_target[nodes[edge['target']]['canon']].append(edge)

    cases = []
    for (canon, authority), labels in sorted(by_designation.items()):
        official = [item for item in labels if item['basis'] == 'source']
        child = min(official or labels, key=lambda row: (row['listed_on'], row['id'] != canon, row['id'], row['k']))
        as_of = child['listed_on']
        frontier, seen, ancestors = [canon], {canon}, {}
        for _ in range(6):
            next_frontier = []
            for target in frontier:
                for edge in by_target[target]:
                    if ((edge.get('valid_from') or '') > as_of
                            or (edge.get('valid_to') and edge['valid_to'] < as_of)):
                        continue
                    parent = nodes[edge['source']]['canon']
                    if parent == canon:
                        continue
                    for label in by_designation.get((parent, authority), []):
                        if _active(label, as_of):
                            ancestors[label['k']] = {**label, 'name': nodes[label['id']]['name']}
                    if parent not in seen:
                        seen.add(parent)
                        next_frontier.append(parent)
            frontier = next_frontier
        if not ancestors:
            continue
        source_dated = child['basis'] == 'source' and any(a['basis'] == 'source' for a in ancestors.values())
        eligible = [a for a in ancestors.values() if not source_dated or a['basis'] == 'source']
        stratum = 'brand_visible' if any(_tokens(nodes[child['id']]['name']) & _tokens(a['name']) for a in eligible) else 'neutral'
        excluded = sorted(row['k'] for row in labels)
        approximate_seeds = [d['k'] for rows in by_designation.values() for d in rows
                             if d['authority'] == authority and d['basis'] != 'source'] if source_dated else []
        prediction = _predict(graph, child['id'], authority, as_of,
                              sorted(set(excluded + approximate_seeds)), clusters[canon])
        cases.append({'id': child['id'], 'name': nodes[child['id']]['name'], 'authority': authority,
                      'as_of': as_of, 'stratum': stratum, 'excluded_designations': excluded,
                      'source_date_basis': 'source_date' if source_dated else 'first_seen_approximation',
                      'ancestors': sorted({a['id'] for a in eligible}), **prediction})

    strata = []
    for authority in ('OFAC', 'EU', 'UK'):
        for basis in ('source_date', 'first_seen_approximation'):
            for stratum in ('brand_visible', 'neutral'):
                rows = [r for r in cases if (r['authority'], r['source_date_basis'], r['stratum']) == (authority, basis, stratum)]
                n, metrics = len(rows), {}
                for key, prefix in [('flagged', 'graph_flagged'), ('blocked', 'graph_blocked'), ('name_hit', 'name_screen')]:
                    measured = sum(r[key] is not None for r in rows)
                    correct = sum(r[key] is True for r in rows)
                    metrics.update({f'{prefix}_count': correct, f'{prefix}_evaluated_n': measured,
                                    f'{prefix}_recall': correct / n if n >= 30 and measured == n else None})
                strata.append({'authority': authority, 'source_date_basis': basis, 'stratum': stratum,
                               'n': n, 'small_n': n < 30, 'error_count': sum(bool(r['errors']) for r in rows), **metrics})

    # Deterministic bounded audit examples; this is not a precision denominator.
    samples, audited = [], 0
    reference_date = max((r['listed_on'] for labels in by_designation.values() for r in labels), default=date.today().isoformat())
    for target in sorted(by_target):
        if audited >= max(0, audit_limit):
            break
        for authority in ('OFAC', 'EU', 'UK'):
            if any(_active(d, reference_date) for d in by_designation.get((target, authority), [])):
                continue
            if not any(by_designation.get((nodes[e['source']]['canon'], authority)) for e in by_target[target]):
                continue
            if audited >= max(0, audit_limit):
                break
            audited += 1
            member = sorted(clusters[target])[0]
            prediction = _predict(graph, member, authority, reference_date, [], clusters[target])
            if prediction['flagged']:
                samples.append({'id': member, 'authority': authority, 'as_of': reference_date, **prediction})
    return {'schema_version': 2, 'graph': graph.name, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'input_counts': {'entities': len(entities), 'designations': len(designations), 'relationships': len(relationships)},
            'caveat': CAVEAT, 'strata': strata, 'cases': cases, 'skipped_invalid_date_records': skipped,
            'errors': [{'id': row['id'], 'authority': row['authority'], 'errors': row['errors']} for row in cases if row['errors']],
            'sample_misses': [row for row in cases if row['flagged'] is False][:20],
            'sample_flagged_but_undesignated': samples[:20], 'audit_candidates_evaluated': audited,
            'method': 'Production evaluate + ownership trace + name screening; target cluster designations excluded. Counts deduplicated by cluster/authority; official and observation dates separated.',
            'limits': ['Small-n strata have no percentages.', 'first_seen is an observation date, not a legal listing date.',
                       'GLEIF accounting consolidation is not legal ownership.', 'Audit examples are bounded and not a precision estimate.']}


def write_report(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'real_e3.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
    lines = ['## Real-data E3', '', report['method'], '', '| Authority | Date basis | Stratum | n | Flagged | Blocked | Name screen | Errors |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in report['strata']:
        counts = [f"{row[prefix + '_count']}/{row['n']}" for prefix in ('graph_flagged', 'graph_blocked', 'name_screen')]
        note = ' (small n)' if row['small_n'] else ''
        lines.append(f"| {row['authority']} | {row['source_date_basis']} | {row['stratum']} | {row['n']}{note} | {' | '.join(counts)} | {row['error_count']} |")
    lines.extend(['', CAVEAT, '', *report['limits']])
    text = '\n'.join(lines) + '\n'
    (output_dir / 'real_e3.md').write_text(text, encoding='utf8')
    golden = output_dir / 'golden_report.md'
    original = golden.read_text(encoding='utf8') if golden.exists() else ''
    original = original.split('<!-- E3 START -->')[0].rstrip()
    golden.write_text(original + '\n\n<!-- E3 START -->\n' + text + '<!-- E3 END -->\n', encoding='utf8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent / 'out')
    parser.add_argument('--audit-limit', type=int, default=20)
    args = parser.parse_args()
    report = run(GraphStore(get_settings())._db.select_graph(args.graph), audit_limit=args.audit_limit)
    write_report(report, args.output_dir)
    print(f"{len(report['cases'])} unique positives; {len(report['errors'])} prediction errors; {args.output_dir / 'real_e3.json'}")
    print(CAVEAT)
    if report['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
