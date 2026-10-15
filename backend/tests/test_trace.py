from shelltrace.graph.trace import trace, trace_cypher


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
