from __future__ import annotations

import re
import time
from contextlib import contextmanager
from threading import Event, Thread
from typing import Any, Callable
from uuid import uuid4

from falkordb import FalkorDB, Graph

from .config import Settings


_WS = re.compile(r"^[a-z0-9_]{1,32}$")
_TIMEOUT_MS = 2000
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


class _GuardedGraph:
    """Forward graph calls only while the caller still owns its Redis lease."""

    __slots__ = ("__graph", "__ensure_lock")

    def __init__(self, graph: Graph, ensure_lock: Callable[[], None]):
        object.__setattr__(self, "_GuardedGraph__graph", graph)
        object.__setattr__(self, "_GuardedGraph__ensure_lock", ensure_lock)

    def __getattribute__(self, name: str):
        if name in {"_GuardedGraph__graph", "_GuardedGraph__ensure_lock"}:
            raise AttributeError(f"{name} is unavailable on a guarded graph")
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        if name in {"client", "schema", "__dict__"} or name.startswith("_"):
            raise AttributeError(f"{name} is unavailable on a guarded graph")

        graph = object.__getattribute__(self, "_GuardedGraph__graph")
        ensure_lock = object.__getattribute__(self, "_GuardedGraph__ensure_lock")
        attr = getattr(graph, name)
        if not callable(attr):
            return attr

        def guarded_call(*args, **kwargs):
            ensure_lock()
            result = attr(*args, **kwargs)
            if isinstance(result, Graph):
                return _GuardedGraph(result, ensure_lock)
            return result

        return guarded_call


def rows(result: Any) -> list[dict[str, Any]]:
    """Convert a FalkorDB result set into ordinary dictionaries."""
    header = getattr(result, "header", None) or []
    values = getattr(result, "result_set", None) or []
    columns = [item[1] if isinstance(item, (tuple, list)) else item for item in header]
    return [dict(zip(columns, row)) for row in values]


def ro(g: Graph, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a query through FalkorDB's server-enforced read-only API."""
    return rows(g.ro_query(cypher, params or {}, timeout=_TIMEOUT_MS))


def rw(g: Graph, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a trusted application query that may mutate the graph."""
    return rows(g.query(cypher, params or {}))


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
        try:
            self._assert_lock_owned(key, token, lost)
            yield lambda: self._assert_lock_owned(key, token, lost)
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

    def _assert_lock_owned(self, key: str, token: str, lost: Event) -> None:
        if lost.is_set():
            raise TimeoutError(f"Lost graph lock: {key}")
        owner = self._db.connection.get(key)
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
