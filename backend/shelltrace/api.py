from __future__ import annotations

import inspect
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from .agent.claude_brain import make_brain
from .agent.ports import McpHttpToolPort
from .agent.report import TemplateWriter, draft_report
from .agent.runner import run_case
from .config import Settings, get_settings
from .db import GraphStore, WorkspaceNameError, ro
from .events import process_designation
from .graph import aliases, evidence
from .graph.alias_judge import AliasJudgement, JevAliasJudge
from .graph.aliases import ClusterTooLarge, IdentifierConflict, MergeNeedsConfirmation
from .graph.ownership import EntityNotFound
from .memory.cases import CaseStore, FourEyesRequired
from .mcp_server import build_mcp
from .models import CaseRequest, DesignationEvent, IsoDate, PackId, ReviewIn, Strict
from .screening import screen_name
from .seed.synthetic import load_synthetic


class WatchIn(Strict):
    active: bool


class AliasJudgeIn(Strict):
    a_id: str = Field(min_length=1, max_length=80)
    b_id: str = Field(min_length=1, max_length=80)


class AliasDecisionIn(Strict):
    a_id: str = Field(min_length=1, max_length=80)
    b_id: str = Field(min_length=1, max_length=80)
    accept: bool
    by: str = Field(min_length=2, max_length=120)
    reason: str = Field(min_length=10, max_length=1000)
    confirm_merge: bool = False


class ScreenNameIn(Strict):
    workspace: str
    entity_id: str
    as_of: IsoDate
    rulepacks: list[PackId]


def create_app(
    settings: Settings | None = None,
    store: GraphStore | None = None,
    port_factory=None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or GraphStore(settings)
    mcp = build_mcp(store)
    port_factory = port_factory or (
        lambda: McpHttpToolPort(settings.mcp_url, settings.mcp_api_key)
    )

    @asynccontextmanager
    async def lifespan(app):
        if store.ping():
            store.provision(settings.default_workspace, seeder=load_synthetic)
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="ShellTrace", version="2.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def mcp_auth(request: Request, call_next):
        if request.url.path.startswith("/mcp") and settings.mcp_api_key:
            if request.headers.get("authorization") != (
                f"Bearer {settings.mcp_api_key}"
            ):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(EntityNotFound)
    async def entity_not_found(_, exc):
        return JSONResponse(
            {"detail": f"entity {exc} not found"},
            status_code=404,
        )

    @app.exception_handler(FourEyesRequired)
    async def four_eyes_required(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(MergeNeedsConfirmation)
    async def merge_needs_confirmation(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(IdentifierConflict)
    async def identifier_conflict(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(ClusterTooLarge)
    async def cluster_too_large(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(WorkspaceNameError)
    async def invalid_workspace(_, exc):
        return JSONResponse({"detail": "invalid workspace"}, status_code=422)

    def ws_graph(workspace: str):
        if workspace not in store.workspaces():
            store.provision(workspace, seeder=load_synthetic)
        return store.workspace(workspace)

    async def run_request(req: CaseRequest):
        graph = ws_graph(req.workspace)
        evidence.get_entity(graph, req.entity_id)
        brain = make_brain(settings) if req.mode == "agent" else None
        candidate = port_factory() if callable(port_factory) else port_factory
        if inspect.isawaitable(candidate):
            candidate = await candidate
        cases = CaseStore(graph)
        if hasattr(candidate, "__aenter__"):
            async with candidate as port:
                return await run_case(
                    req,
                    port,
                    cases,
                    brain,
                    settings,
                    settings.snapshot,
                )
        return await run_case(
            req,
            candidate,
            cases,
            brain,
            settings,
            settings.snapshot,
        )

    def case_store(workspace: str) -> CaseStore:
        return CaseStore(ws_graph(workspace))

    @app.get("/api/health")
    def health():
        graph_name = settings.template_graph
        if not store.ping():
            return {
                "status": "unavailable",
                "graph": graph_name,
                "llm": settings.llm_model if settings.llm_enabled else "deterministic",
                "node_count": 0,
                "llm_provider": settings.llm_provider if settings.llm_enabled else "none",
                "alias_judge": settings.jev_model if settings.jev_enabled and settings.jev_api_key else "disabled",
            }
        rows = ro(store.template(), "MATCH (n) RETURN count(n) AS node_count")
        return {
            "status": "ok",
            "graph": graph_name,
            "llm": settings.llm_model if settings.llm_enabled else "deterministic",
            "node_count": rows[0]["node_count"] if rows else 0,
            "llm_provider": settings.llm_provider if settings.llm_enabled else "none",
            "alias_judge": settings.jev_model if settings.jev_enabled and settings.jev_api_key else "disabled",
        }

    @app.post("/api/aliases/judge")
    async def judge_alias(pair: AliasJudgeIn, workspace: str):
        # This advisory endpoint never provisions workspaces or writes graph state.
        if workspace not in store.workspaces():
            raise HTTPException(status_code=404, detail="workspace not found")
        graph = store.workspace(workspace)
        rows = ro(
            graph,
            "MATCH (a:Entity {id:$a})-[c:CANDIDATE_SAME_AS]-(b:Entity {id:$b}) "
            "WHERE c.state='pending' RETURN properties(a) AS a, properties(b) AS b LIMIT 1",
            {"a": pair.a_id, "b": pair.b_id},
        )
        if not rows:
            raise HTTPException(status_code=404, detail="pending alias candidate not found")
        members = []
        for entity in (rows[0]["a"], rows[0]["b"]):
            members.append(ro(graph, "MATCH (e:Entity) WHERE e.canon=$canon OR e.id=$id RETURN properties(e) AS e LIMIT 26", {"canon": entity.get("canon", entity["id"]), "id": entity["id"]}))
        if any(len(group) > aliases.MAX_CLUSTER for group in members):
            return AliasJudgement(reason="cluster_size_limit")
        for left in members[0]:
            for right in members[1]:
                _, _, reason = aliases.score_pair(left["e"], right["e"])
                if reason.startswith("identifier_conflict:"):
                    return AliasJudgement("different_entity", "deterministic", reason)
        judge = JevAliasJudge(settings.jev_api_key if settings.jev_enabled else None, settings.jev_model, timeout_s=settings.jev_timeout_s)
        return await judge.judge(rows[0]["a"], rows[0]["b"])

    @app.get("/api/entities/search")
    def search_entities(
        workspace: str,
        q: str = Query(min_length=2, max_length=120),
        limit: int = Query(default=8, ge=1, le=20),
    ):
        return {"hits": evidence.entity_search(ws_graph(workspace), q, limit)}

    @app.post("/api/cases")
    async def open_case(req: CaseRequest):
        return await run_request(req)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str, workspace: str):
        result = case_store(workspace).get(case_id)
        if result is None:
            raise HTTPException(status_code=404, detail="case not found")
        return result

    @app.post("/api/cases/{case_id}/review")
    def review_case(case_id: str, workspace: str, review: ReviewIn):
        try:
            return case_store(workspace).review(case_id, review)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="case not found") from exc

    @app.post("/api/cases/{case_id}/report")
    async def report_case(case_id: str, workspace: str):
        result = case_store(workspace).get(case_id)
        if result is None:
            raise HTTPException(status_code=404, detail="case not found")
        return await draft_report(result, TemplateWriter())

    @app.post("/api/cases/{case_id}/watch")
    def watch_case(case_id: str, workspace: str, body: WatchIn):
        cases = case_store(workspace)
        if cases.get(case_id) is None:
            raise HTTPException(status_code=404, detail="case not found")
        return cases.set_watch(case_id, body.active)

    @app.post("/api/events/designation")
    async def designation_event(event: DesignationEvent):
        ws_graph(event.workspace)
        return await process_designation(store, event, port_factory, settings)

    @app.get("/api/notifications")
    def notifications(workspace: str, limit: int = Query(default=50, ge=1, le=200)):
        return case_store(workspace).notifications(limit)

    @app.post("/api/aliases/decide")
    def decide_alias(workspace: str, body: AliasDecisionIn):
        return aliases.decide(
            ws_graph(workspace),
            body.a_id,
            body.b_id,
            body.accept,
            body.by,
            body.reason,
            body.confirm_merge,
        )

    @app.post("/api/screen/name")
    def screen_name_endpoint(body: ScreenNameIn):
        return screen_name(
            ws_graph(body.workspace),
            body.entity_id,
            body.rulepacks,
            body.as_of,
        )

    @app.get("/api/subgraph")
    def subgraph(
        workspace: str,
        entity_id: str,
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=50, ge=1, le=50),
    ):
        return evidence.neighborhood(ws_graph(workspace), entity_id, depth, limit)

    @app.get("/api/eval/latest")
    def eval_latest():
        output_dir = Path(__file__).resolve().parents[1] / "eval" / "out"
        golden_path = output_dir / "golden_report.json"
        real_path = output_dir / "real_e3.json"
        markdown_path = output_dir / "golden_report.md"
        golden = (
            json.loads(golden_path.read_text(encoding="utf-8"))
            if golden_path.exists()
            else None
        )
        real_e3 = (
            json.loads(real_path.read_text(encoding="utf-8"))
            if real_path.exists()
            else None
        )
        markdown = (
            markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        )
        return {
            "available": golden is not None or real_e3 is not None or bool(markdown),
            "golden": golden,
            "real_e3": real_e3,
            "markdown": markdown,
        }

    app.mount("/mcp", mcp.streamable_http_app())
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


app = create_app()
