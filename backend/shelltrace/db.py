from __future__ import annotations

import re
import time
from contextlib import contextmanager
from threading import BoundedSemaphore, Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4

from falkordb import FalkorDB, Graph

from .config import Settings


_WS = re.compile(r"^[a-z0-9_]{1,32}$")
_TIMEOUT_MS = 2000
_RO_READ_SLOTS = BoundedSemaphore(16)
_LOCK_TTL_MS = 300_000
_LOCK_WAIT_SECONDS = 30
_READY_VALUE = "ready-v1"
_RENEW_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
_MARK_READY_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('set', KEYS[2], ARGV[2])
    return 1
end
return 0
"""
_CLEAR_READY_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    redis.call('del', KEYS[2])
    return 1
end
return 0
"""


class WorkspaceNameError(ValueError):
    """Raised when a workspace suffix cannot safely form a graph name."""


class _ReadDispatchGate:
    """Coordinate query-send claims with cancellation without locking over I/O."""

    __slots__ = ("_cancel_event", "_deadline", "_lock", "_cancelled", "_in_flight")

    def __init__(
        self,
        cancel_event: Event | None = None,
        deadline: float | None = None,
    ):
        self._cancel_event = cancel_event or Event()
        self._deadline = deadline
        self._lock = Lock()
        self._cancelled = False
        self._in_flight = 0

    def is_cancelled(self) -> bool:
        return (
            self._cancelled
            or self._cancel_event.is_set()
            or (
                self._deadline is not None
                and time.monotonic() >= self._deadline
            )
        )

    def cancel(self) -> None:
        # Publish cancellation first so a sender that has not claimed dispatch
        # cannot pass the gate. Never wait here: the lock protects only the
        # short claim/state update, never the socket send itself.
        self._cancel_event.set()
        if self._lock.acquire(blocking=False):
            try:
                self._cancelled = True
            finally:
                self._lock.release()

    def dispatch(self, send: Callable[[], Any]) -> Any:
        with self._lock:
            if self.is_cancelled():
                raise TimeoutError("graph read was cancelled before command send")
            # This claim is recorded before releasing the lock. A concurrent
            # timeout can then treat this send as already in flight and
            # disconnect its pool best-effort.
            self._in_flight += 1
        try:
            return send()
        finally:
            with self._lock:
                self._in_flight -= 1


class _GuardedGraph:
    """Forward graph calls only while the caller still owns its Redis lease."""

    __slots__ = ("__graph", "__ensure_lock", "__guard_client")

    def __init__(
        self,
        graph: Graph,
        ensure_lock: Callable[..., None],
        guard_client: Any | None = None,
    ):
        object.__setattr__(self, "_GuardedGraph__graph", graph)
        object.__setattr__(self, "_GuardedGraph__ensure_lock", ensure_lock)
        object.__setattr__(self, "_GuardedGraph__guard_client", guard_client)

    def __getattribute__(self, name: str):
        if name in {
            "_GuardedGraph__graph",
            "_GuardedGraph__ensure_lock",
            "_GuardedGraph__guard_client",
        }:
            raise AttributeError(f"{name} is unavailable on a guarded graph")
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        if name in {"client", "schema", "__dict__"} or name.startswith("_"):
            raise AttributeError(f"{name} is unavailable on a guarded graph")

        graph = object.__getattribute__(self, "_GuardedGraph__graph")
        ensure_lock = object.__getattribute__(self, "_GuardedGraph__ensure_lock")
        guard_client = object.__getattribute__(self, "_GuardedGraph__guard_client")
        attr = getattr(graph, name)
        if not callable(attr):
            return attr

        def guarded_call(*args, **kwargs):
            if guard_client is None:
                ensure_lock()
            else:
                ensure_lock(guard_client)
            result = attr(*args, **kwargs)
            if isinstance(result, Graph):
                return _GuardedGraph(result, ensure_lock, guard_client)
            if getattr(result, "_graph", None) is graph:
                # FalkorDB QueryResult retains the graph that produced it.
                # Keep that reference behind the same lease guard so callers
                # cannot make later graph calls through the result object.
                result._graph = self
            return result

        return guarded_call


def rows(result: Any) -> list[dict[str, Any]]:
    """Convert a FalkorDB result set into ordinary dictionaries."""
    header = getattr(result, "header", None) or []
    values = getattr(result, "result_set", None) or []
    columns = [item[1] if isinstance(item, (tuple, list)) else item for item in header]
    return [dict(zip(columns, row)) for row in values]


def ro(
    g: Graph,
    cypher: str,
    params: dict | None = None,
    *,
    timeout_ms: int | None = None,
    socket_timeout_s: float | None = None,
    socket_connect_timeout_s: float | None = None,
    wall_deadline: float | None = None,
) -> list[dict]:
    """Run a query through FalkorDB's server-enforced read-only API."""
    timeout = (
        _TIMEOUT_MS
        if timeout_ms is None
        else max(1, min(_TIMEOUT_MS, int(timeout_ms)))
    )
    if (
        socket_timeout_s is None
        and socket_connect_timeout_s is None
        and wall_deadline is None
    ):
        return rows(g.ro_query(cypher, params or {}, timeout=timeout))
    dispatch_gate = (
        _ReadDispatchGate(deadline=wall_deadline)
        if wall_deadline is not None
        else None
    )
    with graph_with_socket_timeout(
        g,
        socket_timeout_s=socket_timeout_s,
        socket_connect_timeout_s=socket_connect_timeout_s,
        dispatch_gate=dispatch_gate,
    ) as bounded_graph:
        if wall_deadline is None:
            return rows(bounded_graph.ro_query(cypher, params or {}, timeout=timeout))
        return _ro_until_deadline(
            bounded_graph,
            cypher,
            params or {},
            timeout,
            wall_deadline,
            dispatch_gate,
        )


def _ro_until_deadline(
    g: Graph,
    cypher: str,
    params: dict,
    query_timeout_ms: int,
    wall_deadline: float,
    dispatch_gate: _ReadDispatchGate | None,
) -> list[dict]:
    remaining_s = wall_deadline - time.monotonic()
    if remaining_s <= 0:
        raise TimeoutError("graph read exceeded its wall-clock deadline")
    if not _RO_READ_SLOTS.acquire(timeout=remaining_s):
        raise TimeoutError("graph read could not start before its wall-clock deadline")
    completed = Event()
    outcome: dict[str, Any] = {}

    def read() -> None:
        try:
            outcome["rows"] = rows(
                g.ro_query(cypher, params, timeout=query_timeout_ms)
            )
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            completed.set()
            _RO_READ_SLOTS.release()

    worker = Thread(target=read, daemon=True)
    try:
        worker.start()
    except BaseException:
        _RO_READ_SLOTS.release()
        raise
    remaining_s = wall_deadline - time.monotonic()
    if remaining_s <= 0 or not completed.wait(remaining_s):
        if dispatch_gate is not None:
            dispatch_gate.cancel()
        try:
            graph = _unwrapped_graph(g)
            client = graph.client
            redis_client = getattr(client, "connection", client)
            redis_client.connection_pool.disconnect()
        except Exception:
            pass
        raise TimeoutError("graph read exceeded its wall-clock deadline")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["rows"]


def _unwrapped_graph(g: Graph) -> Graph:
    """Return the graph behind an internal lease guard for bounded I/O setup."""
    if isinstance(g, _GuardedGraph):
        return object.__getattribute__(g, "_GuardedGraph__graph")
    return g


def _graph_guard(g: Graph) -> Callable[[], None] | None:
    if isinstance(g, _GuardedGraph):
        return object.__getattribute__(g, "_GuardedGraph__ensure_lock")
    return None


def rw(g: Graph, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a trusted application query that may mutate the graph."""
    return rows(g.query(cypher, params or {}))


@contextmanager
def graph_with_socket_timeout(
    g: Graph,
    *,
    socket_timeout_s: float | None,
    socket_connect_timeout_s: float | None,
    dispatch_gate: _ReadDispatchGate | None = None,
    cancellation_event: Event | None = None,
):
    """Use a temporary client with bounded transport waits for a read operation."""
    raw_graph = _unwrapped_graph(g)
    ensure_lock = _graph_guard(g)
    if dispatch_gate is None and cancellation_event is not None:
        # Keep the cancellation-event hook usable by focused transport tests.
        dispatch_gate = _ReadDispatchGate(cancellation_event)
    try:
        client = raw_graph.client
        redis_client = getattr(client, "connection", client)
        pool = redis_client.connection_pool
        pool_kwargs = dict(pool.connection_kwargs)
    except AttributeError:
        # Lightweight graph doubles may not expose a Redis client. Their query
        # methods still enforce the server timeout.
        yield g
        return

    if socket_timeout_s is not None:
        pool_kwargs["socket_timeout"] = socket_timeout_s
    if socket_connect_timeout_s is not None:
        pool_kwargs["socket_connect_timeout"] = socket_connect_timeout_s
    try:
        connection_class = pool.connection_class
        if dispatch_gate is not None:
            class DeadlineConnection(connection_class):
                def connect(self):
                    if dispatch_gate.is_cancelled():
                        raise TimeoutError("graph read was cancelled before connection")
                    super().connect()
                    if dispatch_gate.is_cancelled():
                        self.disconnect()
                        raise TimeoutError("graph read was cancelled during connection")

                def send_packed_command(self, *args, **kwargs):
                    return dispatch_gate.dispatch(
                        lambda: super(DeadlineConnection, self).send_packed_command(
                            *args, **kwargs
                        )
                    )

            connection_class = DeadlineConnection
        bounded_pool = type(pool)(
            connection_class=connection_class,
            **pool_kwargs,
        )
        bounded_client = type(redis_client)(connection_pool=bounded_pool)
        bounded_graph = type(raw_graph)(bounded_client, raw_graph.name)
        if ensure_lock is not None:
            bounded_graph = _GuardedGraph(
                bounded_graph, ensure_lock, guard_client=bounded_client
            )
    except Exception as exc:
        raise RuntimeError("could not create a graph client with bounded socket waits") from exc

    try:
        yield bounded_graph
    finally:
        try:
            bounded_client.close()
        finally:
            bounded_pool.disconnect()


class GraphStore:
    def __init__(self, settings: Settings):
        global _TIMEOUT_MS
        _TIMEOUT_MS = settings.query_timeout_ms
        self.s = settings
        self._db = FalkorDB(
            host=settings.falkor_host,
            port=settings.falkor_port,
            username=settings.falkor_username,
            password=settings.falkor_password,
        )

    def ping(self) -> bool:
        try:
            self._db.connection.ping()
            return True
        except Exception:
            return False

    def template(self) -> Graph:
        return self._db.select_graph(self.s.template_graph)

    def workspace(self, ws: str) -> Graph:
        if not isinstance(ws, str) or not _WS.fullmatch(ws):
            raise WorkspaceNameError(ws)
        return self._db.select_graph(f"st_ws_{ws}")

    def workspaces(self) -> list[str]:
        return [name[len("st_ws_") :] for name in self._db.list_graphs() if name.startswith("st_ws_")]

    def provision(self, ws: str, seeder: Callable[[Graph], Any], force_seed: bool = False) -> None:
        """Create an isolated tenant graph, copying only a fully seeded template."""
        graph = self.workspace(ws)
        graph_name = f"st_ws_{ws}"
        lock_key = self._lock_key(graph_name)
        token = self._acquire_lock(lock_key, wait_seconds=_LOCK_WAIT_SECONDS)
        with self._renewed_lock(lock_key, token) as ensure_lock:
            if not force_seed and self._is_ready(graph_name):
                return

            if not self._clear_ready_if_owner(graph_name, lock_key, token):
                raise TimeoutError(f"Lost graph lock before provisioning: {graph_name}")
            guarded_graph = _GuardedGraph(graph, ensure_lock)
            try:
                if force_seed:
                    seeder(guarded_graph)
                else:
                    template_ready = self._ensure_template_ready(seeder)
                    existing = set(self._db.list_graphs())
                    if graph_name in existing:
                        # An unmarked graph may be a failed prior seed. Re-seed it
                        # idempotently instead of copying over an unknown state.
                        seeder(guarded_graph)
                    elif template_ready and self._is_ready(self.s.template_graph):
                        try:
                            ensure_lock()
                            self._db.connection.execute_command(
                                "GRAPH.COPY", self.s.template_graph, graph_name
                            )
                        except Exception:
                            seeder(guarded_graph)
                    else:
                        # Another worker is building the template. Never copy it
                        # until its ready marker exists; seed this workspace alone.
                        seeder(guarded_graph)
                ensure_lock()
                if not self._mark_ready_if_owner(graph_name, lock_key, token):
                    raise TimeoutError(f"Lost graph lock before marking ready: {graph_name}")
            except Exception:
                self._clear_ready_if_owner(graph_name, lock_key, token)
                raise

    def drop(self, ws: str) -> None:
        graph_name = f"st_ws_{ws}"
        graph = self.workspace(ws)
        lock_key = self._lock_key(graph_name)
        token = self._acquire_lock(lock_key, wait_seconds=_LOCK_WAIT_SECONDS)
        with self._renewed_lock(lock_key, token) as ensure_lock:
            ensure_lock()
            graph.delete()
            if not self._clear_ready_if_owner(graph_name, lock_key, token):
                raise TimeoutError(f"Lost graph lock before dropping workspace: {graph_name}")

    @staticmethod
    def _lock_key(graph_name: str) -> str:
        return f"shelltrace:graph-lock:{graph_name}"

    @staticmethod
    def _ready_key(graph_name: str) -> str:
        return f"shelltrace:graph-ready:{graph_name}"

    def _is_ready(self, graph_name: str) -> bool:
        if graph_name not in set(self._db.list_graphs()):
            return False
        value = self._db.connection.get(self._ready_key(graph_name))
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="ignore")
        return value == _READY_VALUE

    def _mark_ready_if_owner(self, graph_name: str, lock_key: str, token: str) -> bool:
        return bool(
            self._db.connection.eval(
                _MARK_READY_SCRIPT,
                2,
                lock_key,
                self._ready_key(graph_name),
                token,
                _READY_VALUE,
            )
        )

    def _clear_ready_if_owner(self, graph_name: str, lock_key: str, token: str) -> bool:
        return bool(
            self._db.connection.eval(
                _CLEAR_READY_SCRIPT,
                2,
                lock_key,
                self._ready_key(graph_name),
                token,
            )
        )

    def _acquire_lock(self, key: str, *, wait_seconds: float = 0) -> str:
        token = uuid4().hex
        deadline = time.monotonic() + wait_seconds
        while True:
            if self._db.connection.set(key, token, nx=True, px=_LOCK_TTL_MS):
                return token
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring graph lock: {key}")
            time.sleep(0.05)

    def _release_lock(self, key: str, token: str) -> None:
        self._db.connection.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)

    @contextmanager
    def _renewed_lock(self, key: str, token: str):
        stop = Event()
        lost = Event()
        heartbeat = Thread(
            target=self._renew_lock,
            args=(key, token, stop, lost),
            daemon=True,
        )
        heartbeat.start()

        def ensure_lock(connection=None) -> None:
            self._assert_lock_owned(key, token, lost, connection)

        try:
            ensure_lock()
            yield ensure_lock
        finally:
            stop.set()
            heartbeat.join()
            self._release_lock(key, token)

    def _renew_lock(self, key: str, token: str, stop: Event, lost: Event) -> None:
        ttl_seconds = _LOCK_TTL_MS / 1000
        interval_seconds = max(0.001, min(ttl_seconds / 4, 30.0))

        while not stop.wait(interval_seconds):
            retry_seconds = 0.01
            while not stop.is_set():
                try:
                    renewed = self._db.connection.eval(
                        _RENEW_LOCK_SCRIPT, 1, key, token, _LOCK_TTL_MS
                    )
                except Exception:
                    # An EVAL transport failure does not tell us whether Redis
                    # extended the lease. Retry while guarded graph calls keep
                    # fencing work and stop interrupts the retry on context exit.
                    if stop.wait(retry_seconds):
                        return
                    retry_seconds = min(retry_seconds * 2, 1.0)
                    continue

                if not renewed:
                    lost.set()
                    return
                break

    def _assert_lock_owned(
        self, key: str, token: str, lost: Event, connection=None
    ) -> None:
        if lost.is_set():
            raise TimeoutError(f"Lost graph lock: {key}")
        lock_client = self._db.connection if connection is None else connection
        owner = lock_client.get(key)
        if isinstance(owner, bytes):
            owner = owner.decode("ascii", errors="ignore")
        if owner != token:
            lost.set()
            raise TimeoutError(f"Lost graph lock: {key}")

    def _ensure_template_ready(self, seeder: Callable[[Graph], Any]) -> bool:
        graph_name = self.s.template_graph
        if self._is_ready(graph_name):
            return True
        lock_key = self._lock_key(graph_name)
        lock_token = uuid4().hex
        acquired = self._db.connection.set(
            lock_key, lock_token, nx=True, px=_LOCK_TTL_MS
        )
        if not acquired:
            # The owner may have finished between our readiness check and lock
            # attempt. If not, the caller safely seeds its own graph.
            return self._is_ready(graph_name)

        with self._renewed_lock(lock_key, lock_token) as ensure_lock:
            if self._is_ready(graph_name):
                return True
            if not self._clear_ready_if_owner(graph_name, lock_key, lock_token):
                raise TimeoutError(f"Lost graph lock before seeding template: {graph_name}")
            try:
                seeder(_GuardedGraph(self.template(), ensure_lock))
                ensure_lock()
                if not self._mark_ready_if_owner(graph_name, lock_key, lock_token):
                    raise TimeoutError(f"Lost graph lock before marking template ready: {graph_name}")
            except Exception:
                self._clear_ready_if_owner(graph_name, lock_key, lock_token)
                raise
            return True


@contextmanager
def graph_operation_lock(g: Graph):
    """Serialize a multi-query graph mutation across processes by graph name."""
    connection = g.client.connection
    lock_key = GraphStore._lock_key(g.name)
    token = uuid4().hex
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while not connection.set(lock_key, token, nx=True, px=_LOCK_TTL_MS):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out acquiring graph lock: {lock_key}")
        time.sleep(0.05)

    stop = Event()
    lost = Event()

    def ensure_lock(read_client=None) -> None:
        if lost.is_set():
            raise TimeoutError(f"Lost graph lock: {lock_key}")
        lock_client = connection if read_client is None else read_client
        owner = lock_client.get(lock_key)
        if isinstance(owner, bytes):
            owner = owner.decode("ascii", errors="ignore")
        if owner != token:
            lost.set()
            raise TimeoutError(f"Lost graph lock: {lock_key}")

    def renew() -> None:
        ttl_seconds = _LOCK_TTL_MS / 1000
        interval_seconds = max(0.001, min(ttl_seconds / 4, 30.0))
        while not stop.wait(interval_seconds):
            retry_seconds = 0.01
            while not stop.is_set():
                try:
                    renewed = connection.eval(
                        _RENEW_LOCK_SCRIPT, 1, lock_key, token, _LOCK_TTL_MS
                    )
                except Exception:
                    if stop.wait(retry_seconds):
                        return
                    retry_seconds = min(retry_seconds * 2, 1.0)
                    continue
                if not renewed:
                    lost.set()
                break
            if lost.is_set():
                return

    heartbeat = Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        ensure_lock()
        yield _GuardedGraph(g, ensure_lock)
        ensure_lock()
    finally:
        stop.set()
        heartbeat.join()
        connection.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, token)
