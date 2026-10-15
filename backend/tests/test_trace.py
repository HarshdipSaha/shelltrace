from types import SimpleNamespace
from uuid import uuid4

import pytest

from shelltrace.db import rw
from shelltrace.graph.trace import TraceUnavailable, trace, trace_cypher
from shelltrace.seed.synthetic import load_synthetic
from shelltrace.graph import trace as trace_module


ALL = ("OFAC", "EU", "UK")


def test_hero_trace_goes_through_accepted_alias(store, golden_ws):
    result = trace(
        store.workspace(golden_ws), "c_nordharbor", "2024-01-01", 6, ALL
    )

    assert result.hops == 4
    assert [edge.type for edge in result.edges].count("SAME_AS") == 1
    assert result.nodes[0].id == "p_volkov"
    assert result.nodes[-1].id == "c_nordharbor"


def test_longer_valid_path_beats_expired_shortcut(store, golden_ws):
    graph = store.workspace(golden_ws)

    current = trace(graph, "c_nordharbor", "2024-01-01", 6, ALL)
    earlier = trace(graph, "c_nordharbor", "2020-06-01", 6, ALL)

    assert current.nodes[0].id == "p_volkov"
    assert (earlier.hops, earlier.nodes[0].id) == (1, "p_sokolov")


def test_clear_entity_has_no_trace(store, golden_ws):
    assert trace(store.workspace(golden_ws), "c_aegean", "2024-01-01", 6, ALL) is None


def test_zero_hop_trace_returns_designation(store, golden_ws):
    result = trace(store.workspace(golden_ws), "c_rostok", "2024-01-01", 6, ALL)

    assert result.hops == 0
    assert result.edges == []
    assert len(result.nodes) == 1
    assert result.designation_key.startswith("syn:D-c_rostok")


def test_excluding_direct_designation_removes_zero_hop_trace(store, golden_ws):
    assert trace(
        store.workspace(golden_ws),
        "c_rostok",
        "2024-01-01",
        6,
        ("OFAC",),
        exclude=("syn:D-c_rostok-prog_ofac",),
    ) is None


def test_authority_filter_applies_to_zero_hop_and_paths(store, golden_ws):
    graph = store.workspace(golden_ws)

    assert trace(graph, "c_harbour_trading", "2024-01-01", 6, ("UK",)) is None
    result = trace(graph, "c_harbour_trading", "2024-01-01", 6, ("OFAC",))

    assert result.hops == 0


def test_context_trace_preserves_actual_edge_endpoints(store, golden_ws):
    result = trace(
        store.workspace(golden_ws),
        "c_cynominee",
        "2024-01-01",
        4,
        ALL,
        mode="context",
    )

    assert result is not None
    assert any(
        edge.type == "OFFICER_OF"
        and edge.from_id == "p_elena"
        and edge.to_id == "c_meridian"
        for edge in result.edges
    )


def test_candidate_alias_does_not_create_a_trace(store, golden_ws):
    assert trace(
        store.workspace(golden_ws), "c_harbor_trading", "2024-01-01", 6, ("OFAC",)
    ) is None


def test_trace_query_filters_dates_inside_a_bounded_path():
    query = trace_cypher(9, "ownership")

    assert "[:OWNS|CONTROLS|SAME_AS*1..6]" in query
    assert "all(r IN relationships(p) WHERE" in query
    assert "r.valid_from <= $as_of" in query
    assert "r.valid_to >= $as_of" in query
    assert "CANDIDATE_SAME_AS" not in query


def test_trace_path_candidate_cap_returns_unavailable_not_no_trace(
    store, monkeypatch
):
    workspace = f"t_trace_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    graph = store.workspace(workspace)
    monkeypatch.setattr(trace_module, "TRACE_PATH_CANDIDATE_BUDGET", 2)
    try:
        rw(
            graph,
            "CREATE (p:Program {id:'trace_prog', authority:'OFAC', name:'Trace Test'}), "
            "(target:Entity {id:'trace_target', name:'Trace Target', kind:'Company', country:'HK', canon:'trace_target'}) "
            "WITH p, target UNWIND range(0, 2) AS i "
            "CREATE (source:Entity {id:'trace_source_' + toString(i), name:'Trace Source ' + toString(i), "
            "kind:'Company', country:'HK'}) "
            "WITH source, p, target, i "
            "CREATE (source)-[:OWNS {k:'trace_owns_' + toString(i), valid_from:'2020-01-01'}]->(target) "
            "WITH source, p, i "
            "CREATE (source)-[:DESIGNATED {k:'trace_designation_' + toString(i), "
            "listed_on:'2020-01-01'}]->(p)",
        )

        with pytest.raises(TraceUnavailable, match="candidate path cap"):
            trace(graph, "trace_target", "2024-01-01", 6, ("OFAC",))
    finally:
        store.drop(workspace)


def test_trace_query_failure_is_explicitly_unavailable(store, golden_ws, monkeypatch):
    def fail_query(*args, **kwargs):
        raise TimeoutError("simulated FalkorDB query timeout")

    monkeypatch.setattr(trace_module, "ro", fail_query)

    with pytest.raises(TraceUnavailable, match="trace query failed"):
        trace(store.workspace(golden_ws), "c_nordharbor", "2024-01-01", 6, ALL)


def test_trace_stops_before_exceeding_tool_deadline(monkeypatch):
    clock = {"now": 0.0}
    query_timeouts = []
    socket_timeouts = []

    monkeypatch.setattr(
        trace_module,
        "get_settings",
        lambda: SimpleNamespace(tool_timeout_s=2.0),
        raising=False,
    )
    monkeypatch.setattr(
        trace_module, "monotonic", lambda: clock["now"], raising=False
    )

    def entity_exists(
        _graph,
        _entity_id,
        *,
        timeout_ms=None,
        socket_timeout_s=None,
        socket_connect_timeout_s=None,
        wall_deadline=None,
    ):
        assert timeout_ms is not None and timeout_ms <= 1600
        assert wall_deadline == 1.8
        socket_timeouts.append((socket_timeout_s, socket_connect_timeout_s))

    def slow_zero_hop(
        _graph,
        _cypher,
        _params=None,
        *,
        timeout_ms=None,
        socket_timeout_s=None,
        socket_connect_timeout_s=None,
        wall_deadline=None,
    ):
        query_timeouts.append(timeout_ms)
        assert wall_deadline == 1.8
        socket_timeouts.append((socket_timeout_s, socket_connect_timeout_s))
        clock["now"] = 1.7
        return []

    monkeypatch.setattr(trace_module, "canon_of", entity_exists)
    monkeypatch.setattr(trace_module, "ro", slow_zero_hop)

    with pytest.raises(TraceUnavailable, match="deadline"):
        trace(object(), "target", "2024-01-01", 6, ALL)

    assert query_timeouts == [1600]
    assert socket_timeouts == [(1.7, 0.1), (1.7, 0.1)]
