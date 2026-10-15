from dataclasses import FrozenInstanceError
from threading import Event, Lock, Thread
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


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.lock = Lock()
        self.graphs = {}
        self.unsafe_copy = False
        self.copy_calls = []

    def set(self, name, value, *, nx=False, px=None):
        with self.lock:
            if nx and name in self.values:
                return None
            self.values[name] = value
            return True

    def get(self, name):
        with self.lock:
            return self.values.get(name)

    def delete(self, name):
        with self.lock:
            return int(self.values.pop(name, None) is not None)

    def eval(self, script, numkeys, key, token):
        with self.lock:
            if self.values.get(key) == token:
                del self.values[key]
                return 1
            return 0

    def execute_command(self, command, source, destination):
        assert command == "GRAPH.COPY"
        with self.lock:
            if self.graphs.get(source) != "complete":
                self.unsafe_copy = True
                raise RuntimeError("template copy attempted before complete seed")
            self.graphs[destination] = self.graphs[source]
            self.copy_calls.append((source, destination))


class _FakeGraph:
    def __init__(self, name, connection):
        self.name = name
        self.connection = connection

    def delete(self):
        with self.connection.lock:
            self.connection.graphs.pop(self.name, None)


class _FakeFalkorDB:
    def __init__(self, connection):
        self.connection = connection

    def select_graph(self, name):
        return _FakeGraph(name, self.connection)

    def list_graphs(self):
        with self.connection.lock:
            return list(self.connection.graphs)


def _fake_store(monkeypatch, connection):
    import shelltrace.db as db

    monkeypatch.setattr(db, "FalkorDB", lambda **kwargs: _FakeFalkorDB(connection))
    return db.GraphStore(Settings(template_graph="st_facts_test"))


def test_concurrent_template_seed_never_copies_partial_graph(monkeypatch):
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    template_started = Event()
    finish_template = Event()
    failures = []

    def seeder(graph):
        if graph.name == "st_facts_test":
            template_started.set()
            with connection.lock:
                connection.graphs[graph.name] = "partial"
            if not finish_template.wait(timeout=5):
                raise TimeoutError("template seed was not released")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def provision(workspace):
        try:
            store.provision(workspace, seeder)
        except Exception as exc:  # surfaced in the main test thread
            failures.append(exc)

    first = Thread(target=provision, args=("t_concurrent_a",))
    first.start()
    assert template_started.wait(timeout=2)
    second = Thread(target=provision, args=("t_concurrent_b",))
    second.start()
    second.join(timeout=2)
    try:
        assert not second.is_alive(), "contending provision should seed its own graph"
        assert connection.graphs.get("st_ws_t_concurrent_b") == "complete"
        assert connection.copy_calls == []
        assert not connection.unsafe_copy
    finally:
        finish_template.set()
        first.join(timeout=5)

    assert not first.is_alive()
    assert failures == []
    assert connection.copy_calls == [("st_facts_test", "st_ws_t_concurrent_a")]
    assert not connection.unsafe_copy


def test_failed_template_seed_is_retried_before_any_copy(monkeypatch):
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    template_attempts = 0
    ready_key = "shelltrace:graph-ready:st_facts_test"

    def seeder(graph):
        nonlocal template_attempts
        if graph.name == "st_facts_test":
            template_attempts += 1
            with connection.lock:
                connection.graphs[graph.name] = "partial"
            if template_attempts == 1:
                raise RuntimeError("injected seed failure")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    with pytest.raises(RuntimeError, match="injected seed failure"):
        store.provision("t_retry_a", seeder)
    assert connection.get(ready_key) is None
    assert connection.copy_calls == []

    store.provision("t_retry_b", seeder)

    assert template_attempts == 2
    assert connection.get(ready_key) == "ready-v1"
    assert connection.copy_calls == [("st_facts_test", "st_ws_t_retry_b")]
    assert not connection.unsafe_copy


def test_failed_workspace_seed_is_not_ready_and_is_retried(monkeypatch):
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    connection.set("shelltrace:graph-lock:st_facts_test", "other-worker", nx=True, px=300_000)
    workspace = "t_workspace_retry"
    workspace_name = f"st_ws_{workspace}"
    ready_key = f"shelltrace:graph-ready:{workspace_name}"
    attempts = 0

    def seeder(graph):
        nonlocal attempts
        if graph.name != workspace_name:
            raise AssertionError("template seeder should remain owned by the other worker")
        attempts += 1
        with connection.lock:
            connection.graphs[graph.name] = "partial"
        if attempts == 1:
            raise RuntimeError("injected workspace seed failure")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    with pytest.raises(RuntimeError, match="injected workspace seed failure"):
        store.provision(workspace, seeder)
    assert connection.get(ready_key) is None

    store.provision(workspace, seeder)

    assert attempts == 2
    assert connection.get(ready_key) == "ready-v1"
    assert connection.graphs[workspace_name] == "complete"
    assert connection.copy_calls == []
