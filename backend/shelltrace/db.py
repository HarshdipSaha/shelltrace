from __future__ import annotations

import re
from typing import Any, Callable

from falkordb import FalkorDB, Graph

from .config import Settings


_WS = re.compile(r"^[a-z0-9_]{1,32}$")
_READ_TIMEOUT_MS = 2000


class WorkspaceNameError(ValueError):
    """Raised when a workspace suffix cannot safely form a graph name."""


def rows(result: Any) -> list[dict[str, Any]]:
    """Convert a FalkorDB result set into ordinary dictionaries."""
    header = getattr(result, "header", None) or []
    values = getattr(result, "result_set", None) or []
    columns = [item[1] if isinstance(item, (tuple, list)) else item for item in header]
    return [dict(zip(columns, row)) for row in values]


def ro(g: Graph, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a query through FalkorDB's server-enforced read-only API, capped at 2s."""
    return rows(g.ro_query(cypher, params or {}, timeout=_READ_TIMEOUT_MS))


def rw(g: Graph, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a trusted application query that may mutate the graph."""
    return rows(g.query(cypher, params or {}))


class GraphStore:
    def __init__(self, settings: Settings):
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
        """Create a tenant graph from the facts template, seeding if it is absent."""
        graph = self.workspace(ws)
        existing = set(self._db.list_graphs())
        graph_name = f"st_ws_{ws}"
        if graph_name in existing and not force_seed:
            return
        if force_seed:
            seeder(graph)
            return

        if self.s.template_graph not in existing:
            seeder(self.template())
        try:
            self._db.connection.execute_command("GRAPH.COPY", self.s.template_graph, graph_name)
        except Exception:
            seeder(graph)

    def drop(self, ws: str) -> None:
        self.workspace(ws).delete()
