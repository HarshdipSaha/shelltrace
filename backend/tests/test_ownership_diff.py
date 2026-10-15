from uuid import uuid4

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from shelltrace.db import ro, rw
from shelltrace.graph.ownership import evaluate, upstream_scope
from shelltrace.graph.reference import RefEdge, RefGraph, ref_evaluate
from shelltrace.rulepacks import PACKS


edges_st = st.lists(
    st.tuples(
        st.integers(0, 7),
        st.integers(0, 7),
        st.one_of(st.none(), st.sampled_from([10.0, 25.0, 30.0, 45.0, 50.0, 55.0, 60.0, 100.0])),
    ),
    min_size=1,
    max_size=16,
)


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    edges=edges_st,
    seed_nodes=st.sets(st.integers(0, 7), max_size=2),
    target_index=st.integers(0, 7),
    pack_id=st.sampled_from(["OFAC", "EU", "UK"]),
)
def test_cypher_matches_reference_on_small_cyclic_graphs(
    store, edges, seed_nodes, target_index, pack_id
):
    workspace = f"t_diff_{uuid4().hex[:12]}"
    graph = store.workspace(workspace)
    pack = PACKS[pack_id]
    target = f"n{target_index}"
    ownership = [
        RefEdge(f"r{index}", f"n{src}", f"n{dst}", pct)
        for index, (src, dst, pct) in enumerate(edges)
        if src != dst
    ]
    seeds = {f"n{index}": (f"d{index}",) for index in sorted(seed_nodes)}

    try:
        rw(
            graph,
            "UNWIND $nodes AS row MERGE (e:Entity {id:row.id}) "
            "SET e.canon=row.id, e.name=row.id, e.kind='Company'",
            {"nodes": [{"id": f"n{index}"} for index in range(8)]},
        )
        rw(
            graph,
            "UNWIND $rows AS row MATCH (o:Entity {id:row.src}), (x:Entity {id:row.dst}) "
            "CREATE (o)-[:OWNS {k:row.k, pct:row.pct, pct_basis:'synthetic'}]->(x)",
            {
                "rows": [
                    {"k": edge.k, "src": edge.src, "dst": edge.dst, "pct": edge.pct}
                    for edge in ownership
                ]
            },
        )
        rw(
            graph,
            "MERGE (p:Program {id:$program}) SET p.authority=$authority, p.name=$program",
            {"program": f"prog_{pack_id.lower()}", "authority": pack_id},
        )
        rw(
            graph,
            "UNWIND $rows AS row MATCH (e:Entity {id:row.entity}), (p:Program {id:$program}) "
            "CREATE (e)-[:DESIGNATED {k:row.k, listed_on:'2000-01-01'}]->(p)",
            {
                "program": f"prog_{pack_id.lower()}",
                "rows": [{"entity": entity, "k": key} for entity, (key,) in seeds.items()],
            },
        )

        result = evaluate(graph, target, "2024-01-01", pack)
        scope, _ = upstream_scope(graph, target, "2024-01-01", max_hops=6)
        scoped_nodes = set(scope)
        reference_graph = RefGraph(
            tuple(edge for edge in ownership if edge.src in scoped_nodes and edge.dst in scoped_nodes),
            (),
            {node: keys for node, keys in seeds.items() if node in scoped_nodes},
        )
        expected = ref_evaluate(target, reference_graph, pack)

        assert result.verdict == expected.verdict
        assert result.lo == pytest.approx(expected.lo)
        assert result.hi == pytest.approx(expected.hi)
        assert set(result.proof) == set(expected.proof)
        assert set(result.decisive) == set(expected.decisive)
    finally:
        store.drop(workspace)
