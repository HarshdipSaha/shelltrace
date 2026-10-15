from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from shelltrace.config import Settings
from shelltrace.db import WorkspaceNameError, ro, rw, rows


@pytest.mark.parametrize("bad", ["", "Demo", "a-b", "x" * 33, "../etc"])
def test_workspace_rejects_names_outside_safe_grammar(store, bad):
    with pytest.raises(WorkspaceNameError):
        store.workspace(bad)


def test_settings_are_frozen():
    settings = Settings()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        settings.scope_cap = 12


def test_read_only_helper_rejects_write_on_real_graph_api(store, golden_ws):
    graph = store.workspace(golden_ws)
    with pytest.raises(Exception):
        ro(graph, "CREATE (:Hack {x:1})")
    assert ro(graph, "MATCH (n:Hack) RETURN count(n) AS n")[0]["n"] == 0


def test_rows_converts_result_header_and_values_to_dicts():
    class Result:
        header = [[0, "id"], [1, "count"]]
        result_set = [["x", 2]]

    assert rows(Result()) == [{"id": "x", "count": 2}]


def test_read_helper_forwards_parameters_and_two_second_timeout():
    class FakeGraph:
        def ro_query(self, cypher, params, timeout):
            self.call = (cypher, params, timeout)

            class Result:
                header = [[0, "value"]]
                result_set = [[params["value"]]]

            return Result()

    graph = FakeGraph()
    assert ro(graph, "RETURN $value AS value", {"value": 3}) == [{"value": 3}]
    assert graph.call == ("RETURN $value AS value", {"value": 3}, 2000)


def test_store_timeout_setting_updates_ro_timeout_and_is_restored():
    import shelltrace.db as db

    class RecordingGraph:
        def ro_query(self, cypher, params, timeout):
            self.timeout = timeout

            class Result:
                header = [[0, "value"]]
                result_set = [[1]]

            return Result()

    original_timeout = db._TIMEOUT_MS
    try:
        db.GraphStore(Settings(query_timeout_ms=1375))
        configured_graph = RecordingGraph()
        assert ro(configured_graph, "RETURN 1 AS value") == [{"value": 1}]
        assert configured_graph.timeout == 1375
    finally:
        db._TIMEOUT_MS = original_timeout

    default_graph = RecordingGraph()
    assert ro(default_graph, "RETURN 1 AS value") == [{"value": 1}]
    assert default_graph.timeout == original_timeout == 2000


def test_read_helper_returns_golden_entity_as_dicts(store, golden_ws):
    graph = store.workspace(golden_ws)
    assert ro(
        graph,
        "MATCH (e:Entity {id:$id}) RETURN e.id AS id, e.name AS name",
        {"id": "c_nordharbor"},
    ) == [{"id": "c_nordharbor", "name": "Nord Harbor Logistics Ltd"}]


def test_provisioned_workspaces_are_isolated(store, golden_ws):
    from shelltrace.seed.synthetic import load_synthetic

    workspace = f"t_iso_{uuid4().hex[:8]}"
    store.provision(workspace, seeder=load_synthetic, force_seed=True)
    try:
        rw(store.workspace(workspace), "MATCH (e:Entity {id:'c_elm'}) SET e.name='changed'")
        assert ro(store.workspace(golden_ws), "MATCH (e:Entity {id:'c_elm'}) RETURN e.name AS n")[0]["n"] == "Elm Fertiliser BV"
    finally:
        store.drop(workspace)


def test_workspace_list_only_returns_workspace_suffixes(store, golden_ws):
    assert golden_ws in store.workspaces()
