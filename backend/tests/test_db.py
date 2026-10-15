from dataclasses import FrozenInstanceError
from threading import Event, Lock, Thread
from time import monotonic
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


def test_graph_with_socket_timeout_uses_and_closes_a_bounded_client():
    from shelltrace.db import graph_with_socket_timeout

    class FakePool:
        connection_class = object

        def __init__(self, connection_class=object, **kwargs):
            self.connection_class = connection_class
            self.connection_kwargs = kwargs
            self.disconnected = False

        def disconnect(self):
            self.disconnected = True

    class FakeRedisClient:
        def __init__(self, connection_pool):
            self.connection_pool = connection_pool
            self.closed = False

        def close(self):
            self.closed = True

    class FakeFalkorDBClient:
        def __init__(self, connection):
            self.connection = connection

    class FakeGraph:
        def __init__(self, client, name):
            self.client = client
            self.name = name

    original = FakeGraph(
        FakeFalkorDBClient(FakeRedisClient(FakePool(socket_timeout=None))),
        "trace_graph",
    )
    with graph_with_socket_timeout(
        original, socket_timeout_s=0.2, socket_connect_timeout_s=0.1
    ) as bounded:
        assert bounded is not original
        assert bounded.name == "trace_graph"
        assert bounded.client.connection_pool.connection_kwargs["socket_timeout"] == 0.2
        assert bounded.client.connection_pool.connection_kwargs["socket_connect_timeout"] == 0.1
        bounded_client = bounded.client
        bounded_pool = bounded.client.connection_pool

    assert bounded_client.closed
    assert bounded_pool.disconnected


def test_timed_out_connection_cannot_issue_a_late_query():
    from threading import Event, Thread

    from shelltrace.db import graph_with_socket_timeout

    connection_started = Event()
    finish_connect = Event()
    cancelled = Event()
    errors = []

    class SlowConnection:
        def __init__(self):
            self.disconnected = False

        def connect(self):
            connection_started.set()
            finish_connect.wait(timeout=2)

        def disconnect(self):
            self.disconnected = True

    class FakePool:
        connection_class = SlowConnection

        def __init__(self, connection_class=SlowConnection, **kwargs):
            self.connection_class = connection_class
            self.connection_kwargs = kwargs
            self.disconnected = False

        def disconnect(self):
            self.disconnected = True

    class FakeRedisClient:
        def __init__(self, connection_pool):
            self.connection_pool = connection_pool

        def close(self):
            pass

    class FakeFalkorDBClient:
        def __init__(self, connection):
            self.connection = connection

    class FakeGraph:
        def __init__(self, client, name):
            self.client = client
            self.name = name

    original = FakeGraph(
        FakeFalkorDBClient(FakeRedisClient(FakePool())), "trace_graph"
    )
    try:
        with graph_with_socket_timeout(
            original,
            socket_timeout_s=0.2,
            socket_connect_timeout_s=0.1,
            cancellation_event=cancelled,
        ) as bounded:
            connection = bounded.client.connection_pool.connection_class()

            def connect():
                try:
                    connection.connect()
                except Exception as exc:
                    errors.append(exc)

            worker = Thread(target=connect, daemon=True)
            worker.start()
            assert connection_started.wait(timeout=0.5)
            cancelled.set()
            finish_connect.set()
            worker.join(timeout=0.5)

            assert not worker.is_alive()
            assert errors and "cancelled during connection" in str(errors[0])
            assert connection.disconnected
    finally:
        finish_connect.set()


def test_cancelled_connection_cannot_send_after_connect():
    from threading import Event

    from shelltrace.db import graph_with_socket_timeout

    cancelled = Event()
    sent_commands = []

    class FakeConnection:
        def connect(self):
            pass

        def disconnect(self):
            pass

        def send_packed_command(self, command, check_health=True):
            sent_commands.append(command)

    class FakePool:
        connection_class = FakeConnection

        def __init__(self, connection_class=FakeConnection, **kwargs):
            self.connection_class = connection_class
            self.connection_kwargs = kwargs

        def disconnect(self):
            pass

    class FakeRedisClient:
        def __init__(self, connection_pool):
            self.connection_pool = connection_pool

        def close(self):
            pass

    class FakeFalkorDBClient:
        def __init__(self, connection):
            self.connection = connection

    class FakeGraph:
        def __init__(self, client, name):
            self.client = client
            self.name = name

    original = FakeGraph(
        FakeFalkorDBClient(FakeRedisClient(FakePool())), "trace_graph"
    )
    with graph_with_socket_timeout(
        original,
        socket_timeout_s=0.2,
        socket_connect_timeout_s=0.1,
        cancellation_event=cancelled,
    ) as bounded:
        connection = bounded.client.connection_pool.connection_class()
        connection.connect()
        cancelled.set()
        with pytest.raises(TimeoutError, match="cancelled before command send"):
            connection.send_packed_command(b"QUERY")

    assert sent_commands == []


def test_dispatch_gate_cancels_new_sends_without_waiting_for_in_flight_send():
    from threading import Event, Thread

    from shelltrace.db import _ReadDispatchGate

    gate = _ReadDispatchGate()
    send_started = Event()
    finish_send = Event()
    results = []

    def send():
        send_started.set()
        finish_send.wait(timeout=2)
        return "sent"

    worker = Thread(target=lambda: results.append(gate.dispatch(send)), daemon=True)
    worker.start()
    try:
        assert send_started.wait(timeout=0.5)
        began = monotonic()
        gate.cancel()
        assert monotonic() - began < 0.1
        with pytest.raises(TimeoutError, match="cancelled"):
            gate.dispatch(lambda: "late send")
    finally:
        finish_send.set()
        worker.join(timeout=0.5)

    assert not worker.is_alive()
    assert results == ["sent"]


def test_dispatch_gate_rejects_sends_after_deadline_before_timeout_worker_runs():
    from shelltrace.db import _ReadDispatchGate

    gate = _ReadDispatchGate(deadline=monotonic() - 0.001)
    sent_commands = []

    with pytest.raises(TimeoutError, match="cancelled"):
        gate.dispatch(lambda: sent_commands.append("late query"))

    assert sent_commands == []


def test_ro_abandons_a_stalled_read_at_wall_deadline():
    from threading import Event

    started = Event()
    release = Event()

    class SlowGraph:
        def ro_query(self, cypher, params, timeout):
            started.set()
            release.wait(timeout=2)

            class Result:
                header = []
                result_set = []

            return Result()

    began = monotonic()
    try:
        with pytest.raises(TimeoutError, match="wall-clock deadline"):
            ro(SlowGraph(), "RETURN 1", wall_deadline=began + 0.05)
        assert started.is_set()
        assert monotonic() - began < 0.5
    finally:
        release.set()


def test_timed_out_guarded_graph_cannot_issue_a_late_query():
    from threading import Event

    from shelltrace.db import _GuardedGraph

    connection_started = Event()
    finish_connect = Event()
    connection_disconnected = Event()
    query_started = Event()
    guard_checks = []

    class SlowConnection:
        def connect(self):
            connection_started.set()
            finish_connect.wait(timeout=2)

        def disconnect(self):
            connection_disconnected.set()

    class FakePool:
        connection_class = SlowConnection

        def __init__(self, connection_class=SlowConnection, **kwargs):
            self.connection_class = connection_class
            self.connection_kwargs = kwargs

        def disconnect(self):
            pass

    class FakeRedisClient:
        def __init__(self, connection_pool):
            self.connection_pool = connection_pool

        def close(self):
            pass

    class FakeFalkorDBClient:
        def __init__(self, connection):
            self.connection = connection

    class FakeGraph:
        def __init__(self, client, name):
            self.client = client
            self.name = name

        def ro_query(self, cypher, params, timeout):
            client = getattr(self.client, "connection", self.client)
            connection_class = client.connection_pool.connection_class
            connection_class().connect()
            query_started.set()

    original = FakeGraph(
        FakeFalkorDBClient(FakeRedisClient(FakePool())), "trace_graph"
    )
    guarded = _GuardedGraph(
        original, lambda connection=None: guard_checks.append(True)
    )
    try:
        with pytest.raises(TimeoutError, match="wall-clock deadline"):
            ro(guarded, "RETURN 1", wall_deadline=monotonic() + 0.15)

        assert connection_started.wait(timeout=0.5)
        finish_connect.set()
        assert connection_disconnected.wait(timeout=0.5)
        assert not query_started.is_set()
        assert guard_checks
    finally:
        finish_connect.set()


def test_timed_out_guarded_lease_check_cannot_issue_a_late_query():
    from threading import Event

    from shelltrace.db import _GuardedGraph

    connection_started = Event()
    finish_connect = Event()
    connection_disconnected = Event()
    graph_query_started = Event()
    checked_connections = []

    class SlowConnection:
        def connect(self):
            connection_started.set()
            finish_connect.wait(timeout=2)

        def disconnect(self):
            connection_disconnected.set()

    class FakePool:
        connection_class = SlowConnection

        def __init__(self, connection_class=SlowConnection, **kwargs):
            self.connection_class = connection_class
            self.connection_kwargs = kwargs

        def disconnect(self):
            pass

    class FakeRedisClient:
        def __init__(self, connection_pool):
            self.connection_pool = connection_pool

        def get(self, key):
            self.connection_pool.connection_class().connect()
            return b"token"

        def close(self):
            pass

    class FakeFalkorDBClient:
        def __init__(self, connection):
            self.connection = connection

    class FakeGraph:
        def __init__(self, client, name):
            self.client = client
            self.name = name

        def ro_query(self, cypher, params, timeout):
            graph_query_started.set()

    original_connection = FakeRedisClient(FakePool())
    original = FakeGraph(
        FakeFalkorDBClient(original_connection), "trace_graph"
    )

    def ensure_lock(connection=None):
        checked_connections.append(connection)
        redis_connection = connection or original_connection
        if redis_connection.get("lock") != b"token":
            raise TimeoutError("Lost graph lock")

    guarded = _GuardedGraph(original, ensure_lock)
    try:
        with pytest.raises(TimeoutError, match="wall-clock deadline"):
            ro(guarded, "RETURN 1", wall_deadline=monotonic() + 0.15)

        assert connection_started.wait(timeout=0.5)
        finish_connect.set()
        assert connection_disconnected.wait(timeout=0.5)
        assert checked_connections and checked_connections[0] is not original_connection
        assert not graph_query_started.is_set()
    finally:
        finish_connect.set()


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
        self.expirations = {}
        self.lock = Lock()
        self.graphs = {}
        self.unsafe_copy = False
        self.copy_calls = []
        self.query_calls = []
        self.renewal_failures = {}
        self.renewal_events = {}

    def _expire_locked(self, name):
        expires_at = self.expirations.get(name)
        if expires_at is not None and monotonic() >= expires_at:
            self.values.pop(name, None)
            self.expirations.pop(name, None)

    def set(self, name, value, *, nx=False, px=None):
        with self.lock:
            self._expire_locked(name)
            if nx and name in self.values:
                return None
            self.values[name] = value
            if px is None:
                self.expirations.pop(name, None)
            else:
                self.expirations[name] = monotonic() + px / 1000
            return True

    def get(self, name):
        with self.lock:
            self._expire_locked(name)
            return self.values.get(name)

    def delete(self, name):
        with self.lock:
            self._expire_locked(name)
            self.expirations.pop(name, None)
            return int(self.values.pop(name, None) is not None)

    def eval(self, script, numkeys, *keys_and_args):
        with self.lock:
            script_lower = script.lower()
            if "pexpire" in script_lower:
                key, token, ttl_ms = keys_and_args
                self._expire_locked(key)
                if self.renewal_failures.get(key, 0):
                    self.renewal_failures[key] -= 1
                    raise ConnectionError("injected transient renewal error")
                if self.values.get(key) == token:
                    self.expirations[key] = monotonic() + int(ttl_ms) / 1000
                    event = self.renewal_events.get(key)
                    if event is not None:
                        event.set()
                    return 1
                return 0
            if "keys[2]" in script_lower:
                lock_key, ready_key, token, *args = keys_and_args
                self._expire_locked(lock_key)
                if self.values.get(lock_key) != token:
                    return 0
                if "redis.call('set'" in script_lower:
                    self.values[ready_key] = args[0]
                    self.expirations.pop(ready_key, None)
                else:
                    self.values.pop(ready_key, None)
                    self.expirations.pop(ready_key, None)
                return 1
            key, token = keys_and_args
            self._expire_locked(key)
            if self.values.get(key) == token:
                del self.values[key]
                self.expirations.pop(key, None)
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

    def query(self, cypher, params=None, timeout=None):
        self.connection.query_calls.append((self.name, cypher, params, timeout))
        return _FakeQueryResult(self)

    def ro_query(self, cypher, params=None, timeout=None):
        self.connection.query_calls.append((self.name, cypher, params, timeout))


class _FakeQueryResult:
    def __init__(self, graph):
        self._graph = graph


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


def test_drop_waits_until_in_progress_provision_finishes(monkeypatch):
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    seed_started = Event()
    finish_seed = Event()
    drop_started = Event()
    failures = []
    workspace = "t_drop_race"
    graph_name = f"st_ws_{workspace}"

    def seeder(graph):
        if graph.name != graph_name:
            raise AssertionError("force_seed must target the workspace")
        with connection.lock:
            connection.graphs[graph.name] = "partial"
        seed_started.set()
        if not finish_seed.wait(timeout=5):
            raise TimeoutError("workspace seed was not released")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def provision():
        try:
            store.provision(workspace, seeder, force_seed=True)
        except Exception as exc:
            failures.append(exc)

    def drop():
        drop_started.set()
        try:
            store.drop(workspace)
        except Exception as exc:
            failures.append(exc)

    provision_thread = Thread(target=provision)
    provision_thread.start()
    assert seed_started.wait(timeout=2)
    drop_thread = Thread(target=drop)
    drop_thread.start()
    assert drop_started.wait(timeout=2)
    Event().wait(0.15)
    try:
        assert drop_thread.is_alive(), "drop should wait for the provision lock"
        assert connection.graphs.get(graph_name) == "partial"
    finally:
        finish_seed.set()
        provision_thread.join(timeout=5)
        drop_thread.join(timeout=5)

    assert not provision_thread.is_alive()
    assert not drop_thread.is_alive()
    assert failures == []
    assert graph_name not in connection.graphs
    assert connection.get(f"shelltrace:graph-ready:{graph_name}") is None


def test_template_lock_renews_beyond_original_ttl(monkeypatch):
    import shelltrace.db as db

    monkeypatch.setattr(db, "_LOCK_TTL_MS", 100)
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    template_started = Event()
    finish_template = Event()
    template_attempts = 0
    failures = []

    def seeder(graph):
        nonlocal template_attempts
        if graph.name == "st_facts_test":
            template_attempts += 1
            with connection.lock:
                connection.graphs[graph.name] = "partial"
            template_started.set()
            if not finish_template.wait(timeout=5):
                raise TimeoutError("template seed was not released")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def provision(workspace):
        try:
            store.provision(workspace, seeder)
        except Exception as exc:
            failures.append(exc)

    first = Thread(target=provision, args=("t_lease_a",))
    first.start()
    assert template_started.wait(timeout=2)
    Event().wait(0.3)  # three times the configured lock TTL
    second = Thread(target=provision, args=("t_lease_b",))
    second.start()
    second.join(timeout=2)
    try:
        assert not second.is_alive(), "a worker should seed its own graph while template lock is held"
        assert template_attempts == 1
        assert connection.graphs.get("st_ws_t_lease_b") == "complete"
        assert connection.copy_calls == []
    finally:
        finish_template.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert failures == []
    assert template_attempts == 1
    assert connection.copy_calls == [("st_facts_test", "st_ws_t_lease_a")]
    assert not connection.unsafe_copy


def test_workspace_lock_renews_beyond_original_ttl(monkeypatch):
    import shelltrace.db as db

    monkeypatch.setattr(db, "_LOCK_TTL_MS", 100)
    connection = _FakeRedis()
    connection.graphs["st_facts_test"] = "complete"
    connection.set("shelltrace:graph-ready:st_facts_test", "ready-v1")
    store = _fake_store(monkeypatch, connection)
    seed_started = Event()
    finish_seed = Event()
    second_seed_entered = Event()
    first_failures = []
    second_failures = []
    workspace = "t_ws_lease"
    graph_name = f"st_ws_{workspace}"

    def blocking_seeder(graph):
        with connection.lock:
            connection.graphs[graph.name] = "partial"
        seed_started.set()
        if not finish_seed.wait(timeout=5):
            raise TimeoutError("workspace seed was not released")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def second_seeder(graph):
        second_seed_entered.set()
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def first_provision():
        try:
            store.provision(workspace, blocking_seeder, force_seed=True)
        except Exception as exc:
            first_failures.append(exc)

    def second_provision():
        try:
            store.provision(workspace, second_seeder)
        except Exception as exc:
            second_failures.append(exc)

    first = Thread(target=first_provision)
    first.start()
    assert seed_started.wait(timeout=2)
    Event().wait(0.3)  # three times the configured lock TTL
    second = Thread(target=second_provision)
    second.start()
    Event().wait(0.15)
    try:
        assert not second_seed_entered.is_set(), "second worker entered while lease should be renewed"
        assert second.is_alive(), "same-workspace provision should wait for the active owner"
        assert connection.graphs.get(graph_name) == "partial"
    finally:
        finish_seed.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert first_failures == []
    assert second_failures == []
    assert not second_seed_entered.is_set()
    assert connection.graphs[graph_name] == "complete"


def test_transient_template_renewal_error_recovers_before_lease_expiry(monkeypatch):
    import shelltrace.db as db

    monkeypatch.setattr(db, "_LOCK_TTL_MS", 100)
    connection = _FakeRedis()
    template_lock_key = "shelltrace:graph-lock:st_facts_test"
    connection.renewal_failures[template_lock_key] = 1
    renewal_succeeded = Event()
    connection.renewal_events[template_lock_key] = renewal_succeeded
    store = _fake_store(monkeypatch, connection)
    template_started = Event()
    finish_template = Event()
    template_attempts = 0
    template_seed_started_at = None
    failures = []

    def seeder(graph):
        nonlocal template_attempts, template_seed_started_at
        if graph.name == "st_facts_test":
            template_attempts += 1
            with connection.lock:
                connection.graphs[graph.name] = "partial"
            template_seed_started_at = monotonic()
            template_started.set()
            if not finish_template.wait(timeout=5):
                raise TimeoutError("template seed was not released")
        with connection.lock:
            connection.graphs[graph.name] = "complete"

    def provision(workspace):
        try:
            store.provision(workspace, seeder)
        except Exception as exc:
            failures.append(exc)

    first = Thread(target=provision, args=("t_renew_retry_a",))
    first.start()
    assert template_started.wait(timeout=2)
    assert renewal_succeeded.wait(timeout=2), "heartbeat did not recover after the transient error"
    remaining_seed_time = template_seed_started_at + 0.3 - monotonic()
    if remaining_seed_time > 0:
        Event().wait(remaining_seed_time)  # keep the seed active beyond the 100 ms TTL
    second = Thread(target=provision, args=("t_renew_retry_b",))
    second.start()
    second.join(timeout=2)
    try:
        assert not second.is_alive(), "a transient renewal error should not strand the worker"
        assert template_attempts == 1
        assert connection.graphs.get("st_ws_t_renew_retry_b") == "complete"
        assert connection.copy_calls == []
    finally:
        finish_template.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert failures == []
    assert template_attempts == 1
    assert connection.copy_calls == [("st_facts_test", "st_ws_t_renew_retry_a")]
    assert not connection.unsafe_copy


def test_replaced_lock_fences_query_result_graph_and_ready_marker(monkeypatch):
    connection = _FakeRedis()
    store = _fake_store(monkeypatch, connection)
    workspace = "t_fenced_seed"
    graph_name = f"st_ws_{workspace}"
    lock_key = f"shelltrace:graph-lock:{graph_name}"
    ready_key = f"shelltrace:graph-ready:{graph_name}"

    def seeder(graph):
        with pytest.raises(AttributeError, match="unavailable on a guarded graph"):
            getattr(graph, "_GuardedGraph__graph")
        result = graph.query("CREATE (:FirstWrite)")
        connection.set(lock_key, "replacement-token", px=300_000)
        result._graph.query("CREATE (:FencedWrite)")

    with pytest.raises(TimeoutError, match="Lost graph lock"):
        store.provision(workspace, seeder, force_seed=True)

    assert connection.query_calls == [(graph_name, "CREATE (:FirstWrite)", None, None)]
    assert connection.get(ready_key) is None
    assert connection.get(lock_key) == "replacement-token"
