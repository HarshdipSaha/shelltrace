"""Explicitly synthetic tiny graphs test evaluation mechanics, not real recall."""
from uuid import uuid4

import pytest

from shelltrace.db import ro, rw
from shelltrace.loaders.common import EdgeRow, NodeRow, load_rows
from shelltrace.schema import ensure_schema


@pytest.fixture
def e3_graph(store):
    graph = store._db.select_graph('e3_regression_' + uuid4().hex[:8])
    ensure_schema(graph)
    nodes = [NodeRow('prog', 'Program', 'OFAC', {'authority': 'OFAC'})]
    nodes += [NodeRow(i, 'Company', name) for i, name in [
        ('parent', 'Acme'), ('child', 'Acme Subsidiary'),
        ('weak', 'Neutral Logistics'), ('alias', 'Neutral Logistics'),
        ('approx', 'Approximate Shipping'), ('unlisted', 'Unlisted Shipping')]]
    def designation(entity, key, basis='source', end=None):
        return EdgeRow(entity, 'prog', 'DESIGNATED', key, {
            'authority': 'OFAC', 'listed_on': '2020-01-01' if entity == 'parent' else '2024-01-01',
            'listed_on_basis': basis, 'delisted_on': end})
    edges = [designation('parent', 'dp'), designation('child', 'dc'),
             designation('child', 'dc_dup'), designation('weak', 'dw'),
             designation('alias', 'da'), designation('approx', 'df', 'first_seen')]
    for target, pct in [('child', 60), ('weak', 10), ('approx', 60), ('unlisted', 60)]:
        edges.append(EdgeRow('parent', target, 'OWNS', 'owns_' + target,
            {'pct': pct, 'pct_basis': 'shareholding', 'valid_from': '2019-01-01'}))
    load_rows(graph, nodes, edges, 'synthetic-e3-regression', 'CC0')
    rw(graph, "MATCH (e:Entity {id:'alias'}) SET e.canon='weak'")
    rw(graph, "MATCH (a:Entity {id:'weak'}),(b:Entity {id:'alias'}) "
        "CREATE (a)-[:SAME_AS {k:'sa1'}]->(b), (b)-[:SAME_AS {k:'sa2'}]->(a)")
    try:
        yield graph
    finally:
        graph.delete()


def test_real_e3_measures_predictions_and_hides_cluster_labels(e3_graph):
    from eval.real_e3 import run
    before = ro(e3_graph, 'MATCH ()-[d:DESIGNATED]->() RETURN count(d) AS n')
    report = run(e3_graph, audit_limit=20)
    cases = {row['id']: row for row in report['cases']}
    assert set(cases) == {'child', 'weak', 'approx'}  # duplicates/aliases cannot inflate n
    assert cases['child']['blocked'] is True
    assert cases['child']['name_hit'] is True
    assert cases['weak']['blocked'] is False  # its own and alias labels were hidden
    assert cases['weak']['flagged'] is True  # a 10% path is a flag, not ownership blocking
    assert cases['weak']['name_hit'] is False
    assert set(cases['weak']['excluded_designations']) == {'dw', 'da'}
    assert cases['approx']['source_date_basis'] == 'first_seen_approximation'
    rows = [r for r in report['strata'] if r['n']]
    assert sum(row['n'] for row in rows) == 3
    assert all(row['small_n'] and row['graph_flagged_recall'] is None for row in rows)
    assert any(r['authority'] == 'EU' and r['n'] == 0 for r in report['strata'])
    assert report['sample_flagged_but_undesignated']
    assert ro(e3_graph, 'MATCH ()-[d:DESIGNATED]->() RETURN count(d) AS n') == before


def test_expired_ownership_or_delisted_parent_is_ineligible(e3_graph):
    from eval.real_e3 import run
    rw(e3_graph, "MATCH ()-[r:OWNS]->() SET r.valid_to='2021-01-01'")
    assert run(e3_graph, audit_limit=0)['cases'] == []
    rw(e3_graph, "MATCH ()-[r:OWNS]->() SET r.valid_to=null")
    rw(e3_graph, "MATCH (:Entity {id:'parent'})-[d:DESIGNATED]->() SET d.delisted_on='2022-01-01'")
    assert run(e3_graph, audit_limit=0)['cases'] == []


def test_errors_are_reported_as_unknown_not_zero_predictions(e3_graph, monkeypatch):
    import eval.real_e3 as module
    def unavailable(*args, **kwargs):
        raise TimeoutError('test query timeout')
    monkeypatch.setattr(module, 'evaluate', unavailable)
    report = module.run(e3_graph, audit_limit=0)
    assert report['errors']
    assert all(row['blocked'] is None for row in report['cases'])
    assert all(row['graph_blocked_recall'] is None for row in report['strata'])


def test_os_ownership_graph_is_rejected(e3_graph):
    from eval.real_e3 import run
    rw(e3_graph, "MATCH ()-[r:OWNS]->() SET r.src='opensanctions:leaky'")
    with pytest.raises(ValueError, match='OpenSanctions ownership'):
        run(e3_graph)


def test_report_output_is_idempotent_and_small_n_has_no_percentages(e3_graph, tmp_path):
    import json
    from eval.real_e3 import run, write_report
    report = run(e3_graph, audit_limit=0)
    (tmp_path/'golden_report.md').write_text('Golden: 24/24\n', encoding='utf8')
    write_report(report, tmp_path)
    write_report(report, tmp_path)
    text = (tmp_path/'golden_report.md').read_text(encoding='utf8')
    assert text.count('## Real-data E3') == 1
    assert text.startswith('Golden: 24/24')
    assert '%' not in text
    assert json.loads((tmp_path/'real_e3.json').read_text(encoding='utf8'))['schema_version'] == 2


def test_fact_tables_are_paged_without_losing_rows(e3_graph):
    from eval.real_e3 import read_table
    query = 'MATCH (e:Entity) RETURN e.id AS id ORDER BY id'
    rows = read_table(e3_graph, query, page_size=2)
    assert len(rows) == 7
    assert len({r['id'] for r in rows}) == 7
