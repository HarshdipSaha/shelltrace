"""Case, step, review, watch, event, and notification persistence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from ..db import graph_operation_lock, ro, rw
from ..models import CaseRequest, CaseResult, PriorCase, ReviewIn, StepIn, StepOut


class FourEyesRequired(Exception):
    """Raised when removing an exposure lacks an independent second reviewer."""


def canonical_json(obj) -> str:
    """Return the canonical JSON representation used for step hashes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def step_hash(prev: str, body: dict) -> str:
    """Hash a canonical step body after its predecessor hash."""
    return hashlib.sha256((prev + canonical_json(body)).encode()).hexdigest()


def _now(*, microseconds: bool = False) -> str:
    precision = "microseconds" if microseconds else "seconds"
    return datetime.now(timezone.utc).isoformat(timespec=precision)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _step_body(row: dict) -> dict:
    """Rebuild the exact StepIn body (plus sequence) from stored properties."""
    return {
        "kind": row["kind"],
        "tool": row.get("tool"),
        "args": json.loads(row["args_json"] or "{}"),
        "result_digest": row.get("result_digest"),
        "evidence_keys": json.loads(row["evidence_json"] or "[]"),
        "probability": row.get("probability"),
        "rationale": row.get("rationale"),
        "latency_ms": row.get("latency_ms", 0),
        "actor": row["actor"],
        "fallback_reason": row.get("fallback_reason"),
        "seq": row["seq"],
    }


OPEN = """CREATE (c:Case {id:$id, entity_id:$entity_id, canon:$canon, workspace:$ws, as_of:$as_of, max_hops:$max_hops,
                         rulepacks_json:$packs, mode:$mode, status:'open', opened_at:$at, snapshot:$snap})
          WITH c MATCH (e:Entity {id:$entity_id}) CREATE (c)-[:ABOUT]->(e)"""
STEP = """MATCH (c:Case {id:$case_id})
          CREATE (c)-[:HAS_STEP]->(s:Step {id:$sid, seq:$seq, kind:$kind, tool:$tool, args_json:$args, result_digest:$digest,
                   evidence_json:$ev, probability:$p, rationale:$rat, latency_ms:$lat, actor:$actor, fallback_reason:$fb,
                   prev_hash:$prev, hash:$hash, at:$at})
          WITH s OPTIONAL MATCH (prev:Step {id:$prev_sid})
          FOREACH (_ IN CASE WHEN prev IS NULL THEN [] ELSE [1] END | CREATE (prev)-[:NEXT]->(s))"""
FINISH = "MATCH (c:Case {id:$id}) SET c.status='done', c.disposition=$disp, c.result_json=$result, c.finished_at=$at"
REVIEW = """MATCH (c:Case {id:$id}) CREATE (c)-[:REVIEWED]->(:Review {reviewer:$reviewer, code:$code, reason:$reason,
            second_reviewer:$second, at:$at}) SET c.review_code=$code"""
WATCH = "MATCH (c:Case {id:$id}) MERGE (c)-[:WATCHES]->(w:Watch {case_id:$id}) SET w.active=$active, w.updated_at=$at"
WATCHED = """MATCH (c:Case)-[:WATCHES]->(w:Watch {active:true}) WHERE c.canon IN $canons
             RETURN c.id AS case_id, c.entity_id AS entity_id, c.as_of AS as_of, c.rulepacks_json AS rulepacks,
                    c.max_hops AS max_hops, c.disposition AS disposition"""
EVENT = """MERGE (e:Event {id:$id}) ON CREATE SET e.kind=$kind, e.payload_json=$payload, e.at=$at, e.fresh_token=$token
          WITH e, e.fresh_token = $token AS fresh REMOVE e.fresh_token RETURN fresh"""
NOTIFY = """MATCH (old:Case {id:$case_id})
          MERGE (n:Notification {id:$nid}) ON CREATE SET n.case_id=$case_id, n.old=$old, n.new=$new, n.diff_json=$diff,
            n.event_id=$eid, n.at=$at, n.fresh_token=$token
          WITH n, old, n.fresh_token = $token AS fresh
          MERGE (n)-[:NOTIFIED]->(old)
          REMOVE n.fresh_token RETURN fresh"""
RECALL = """MATCH (c:Case) WHERE c.canon IN $canons AND c.status = 'done' AND ($exclude IS NULL OR c.id <> $exclude)
            RETURN c.id AS case_id, c.entity_id AS entity_id, c.as_of AS as_of, c.disposition AS disposition,
                   c.opened_at AS opened_at ORDER BY c.opened_at DESC LIMIT $limit"""
NOTIFICATIONS = """MATCH (n:Notification)
                  RETURN n.case_id AS case_id, n.old AS old, n.new AS new,
                         n.diff_json AS diff, n.event_id AS event_id, n.at AS at
                  ORDER BY n.at DESC LIMIT $limit"""


class CaseStore:
    def __init__(self, g):
        self.g = g

    def open(self, req: CaseRequest, canon: str, snapshot: str) -> str:
        case_id = "case_" + uuid4().hex[:12]
        rw(
            self.g,
            OPEN,
            {
                "id": case_id,
                "entity_id": req.entity_id,
                "canon": canon,
                "ws": req.workspace,
                "as_of": req.as_of,
                "max_hops": req.max_hops,
                "packs": _json(req.rulepacks),
                "mode": req.mode,
                "at": _now(),
                "snap": snapshot,
            },
        )
        return case_id

    def append_step(self, case_id: str, step: StepIn) -> StepOut:
        # The sequence read, hash calculation, and write form one graph mutation.
        # Serialize them so concurrent callers cannot fork the audit chain.
        with graph_operation_lock(self.g) as graph:
            cases = CaseStore(graph)
            previous_steps = cases.steps(case_id)
            seq = previous_steps[-1].seq + 1 if previous_steps else 1
            prev_hash = previous_steps[-1].hash if previous_steps else "GENESIS"
            body = step.model_dump() | {"seq": seq}
            digest = step_hash(prev_hash, body)
            at = _now()
            sid = f"{case_id}:{seq:03d}"
            rw(
                graph,
                STEP,
                {
                    "case_id": case_id,
                    "sid": sid,
                    "seq": seq,
                    "kind": step.kind,
                    "tool": step.tool,
                    "args": _json(step.args),
                    "digest": step.result_digest,
                    "ev": _json(step.evidence_keys),
                    "p": step.probability,
                    "rat": step.rationale,
                    "lat": step.latency_ms,
                    "actor": step.actor,
                    "fb": step.fallback_reason,
                    "prev": prev_hash,
                    "hash": digest,
                    "at": at,
                    "prev_sid": f"{case_id}:{seq - 1:03d}" if seq > 1 else None,
                },
            )
        return StepOut(**body, prev_hash=prev_hash, hash=digest, at=at)
    def steps(self, case_id: str) -> list[StepOut]:
        result = ro(
            self.g,
            """MATCH (c:Case {id:$id})-[:HAS_STEP]->(s:Step)
               RETURN s.seq AS seq, s.kind AS kind, s.tool AS tool, s.args_json AS args_json,
                      s.result_digest AS result_digest, s.evidence_json AS evidence_json,
                      s.probability AS probability, s.rationale AS rationale, s.latency_ms AS latency_ms,
                      s.actor AS actor, s.fallback_reason AS fallback_reason, s.prev_hash AS prev_hash,
                      s.hash AS hash, s.at AS at
               ORDER BY s.seq""",
            {"id": case_id},
        )
        steps = []
        for row in result:
            body = _step_body(row)
            steps.append(
                StepOut(
                    **{key: value for key, value in body.items() if key != "seq"},
                    seq=body["seq"],
                    prev_hash=row["prev_hash"],
                    hash=row["hash"],
                    at=row["at"],
                )
            )
        return steps

    def verify_chain(self, case_id: str) -> bool:
        try:
            rows = ro(
                self.g,
                """MATCH (c:Case {id:$id})-[:HAS_STEP]->(s:Step)
                   RETURN s.seq AS seq, s.kind AS kind, s.tool AS tool, s.args_json AS args_json,
                          s.result_digest AS result_digest, s.evidence_json AS evidence_json,
                          s.probability AS probability, s.rationale AS rationale, s.latency_ms AS latency_ms,
                          s.actor AS actor, s.fallback_reason AS fallback_reason, s.prev_hash AS prev_hash,
                          s.hash AS hash
                   ORDER BY s.seq""",
                {"id": case_id},
            )
            expected_prev = "GENESIS"
            for expected_seq, row in enumerate(rows, start=1):
                if row["seq"] != expected_seq or row["prev_hash"] != expected_prev:
                    return False
                digest = step_hash(expected_prev, _step_body(row))
                if row["hash"] != digest:
                    return False
                expected_prev = digest
            return True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    def finish(self, case_id: str, result: CaseResult) -> None:
        with graph_operation_lock(self.g) as graph:
            rows = ro(
                graph,
                """MATCH (c:Case {id:$id}) OPTIONAL MATCH (c)-[:REVIEWED]->(r:Review)
                   RETURN c.status AS status, count(r) AS reviews""",
                {"id": case_id},
            )
            if not rows:
                raise KeyError(case_id)
            if rows[0]["status"] != "open" or rows[0]["reviews"]:
                raise ValueError("case is already finalized")
            rw(
                graph,
                FINISH,
                {
                    "id": case_id,
                    "disp": result.disposition,
                    "result": result.model_dump_json(),
                    "at": _now(),
                },
            )
    def get(self, case_id: str) -> CaseResult | None:
        result = ro(self.g, "MATCH (c:Case {id:$id}) RETURN c.result_json AS result", {"id": case_id})
        if not result or not result[0].get("result"):
            return None
        return CaseResult.model_validate_json(result[0]["result"])

    def reviews(self, case_id: str) -> list[dict] | None:
        """Return a case's persisted review history, newest first, or None if absent."""
        rows = ro(
            self.g,
            """MATCH (c:Case {id:$id})
               OPTIONAL MATCH (c)-[:REVIEWED]->(r:Review)
               RETURN c.id AS case_id, r.reviewer AS reviewer, r.second_reviewer AS second_reviewer,
                      r.code AS code, r.reason AS reason, r.at AS at
               ORDER BY r.at DESC""",
            {"id": case_id},
        )
        if not rows:
            return None
        return [
            {key: row.get(key) for key in ("case_id", "reviewer", "second_reviewer", "code", "reason", "at")}
            for row in rows
            if row.get("reviewer") is not None
        ]

    def review(self, case_id: str, rv: ReviewIn) -> dict:
        with graph_operation_lock(self.g) as graph:
            case_rows = ro(
                graph,
                "MATCH (c:Case {id:$id}) RETURN c.status AS status, c.disposition AS disposition",
                {"id": case_id},
            )
            if not case_rows:
                raise KeyError(case_id)
            if case_rows[0]["status"] != "done":
                raise ValueError("case must be finalized before review")
            disposition = case_rows[0].get("disposition")
            removes_exposure = disposition == "EXPOSED" and rv.code in {
                "CONFIRMED_CLEAR",
                "FALSE_POSITIVE_ALIAS",
                "OVERRIDDEN",
            }
            if removes_exposure and (not rv.second_reviewer or rv.second_reviewer == rv.reviewer):
                raise FourEyesRequired("a second reviewer is required to remove an exposure")

            at = _now()
            rw(
                graph,
                REVIEW,
                {
                    "id": case_id,
                    "reviewer": rv.reviewer,
                    "code": rv.code,
                    "reason": rv.reason,
                    "second": rv.second_reviewer,
                    "at": at,
                },
            )
        return rv.model_dump() | {"case_id": case_id, "at": at}
    def recall(
        self, canons: list[str], exclude_case: str | None = None, limit: int = 10
    ) -> list[PriorCase]:
        result = ro(
            self.g,
            RECALL,
            {"canons": canons, "exclude": exclude_case, "limit": max(0, int(limit))},
        )
        return [PriorCase(**row) for row in result]

    def set_watch(self, case_id: str, active: bool) -> dict:
        at = _now()
        rw(self.g, WATCH, {"id": case_id, "active": bool(active), "at": at})
        return {"case_id": case_id, "active": bool(active), "updated_at": at}

    def watched_cases(self, canons: list[str]) -> list[dict]:
        result = ro(self.g, WATCHED, {"canons": canons})
        watched = []
        for row in result:
            watched.append(
                {
                    "case_id": row["case_id"],
                    "entity_id": row["entity_id"],
                    "as_of": row["as_of"],
                    "rulepacks": json.loads(row["rulepacks"] or "[]"),
                    "max_hops": row["max_hops"],
                    "disposition": row.get("disposition"),
                }
            )
        return watched

    def record_event(self, event_id: str, kind: str, payload: dict) -> bool:
        result = rw(
            self.g,
            EVENT,
            {
                "id": event_id,
                "kind": kind,
                "payload": _json(payload),
                "at": _now(microseconds=True),
                "token": uuid4().hex,
            },
        )
        return bool(result and result[0].get("fresh"))
    def notify(self, event_id: str, case_id: str, old: str, new: str, diff: dict) -> bool:
        notification_id = hashlib.sha1(f"{event_id}|{case_id}".encode()).hexdigest()
        result = rw(
            self.g,
            NOTIFY,
            {
                "nid": notification_id,
                "case_id": case_id,
                "old": old,
                "new": new,
                "diff": _json(diff),
                "eid": event_id,
                "at": _now(microseconds=True),
                "token": uuid4().hex,
            },
        )
        return bool(result and result[0].get("fresh"))

    def notifications(self, limit: int = 50) -> list[dict]:
        result = ro(self.g, NOTIFICATIONS, {"limit": max(0, int(limit))})
        return [
            {
                "case_id": row["case_id"],
                "old": row["old"],
                "new": row["new"],
                "diff": json.loads(row["diff"] or "{}"),
                "event_id": row["event_id"],
                "at": row["at"],
            }
            for row in result
        ]
