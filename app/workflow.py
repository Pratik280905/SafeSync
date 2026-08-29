from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.agents import assess_incident
from app.clocks import IST, due_at
from app.db import audit
from app.retrieve import Retriever, flatten_clauses, keyword_boost, merge_retrieval


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def persist_assessment(conn, incident: dict, site: dict, clauses: list[dict], result: dict) -> dict:
    inc_id = incident["incident_id"]
    for role in ("analyst", "verifier"):
        payload = result[role]
        meta = result[f"{role}_meta"]
        conn.execute(
            """INSERT INTO assessments (incident_id, agent_role, model, reportable, confidence, payload, parse_status, latency_ms)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                inc_id,
                role,
                meta["model"],
                1 if payload.get("reportable") else 0,
                payload.get("confidence"),
                json.dumps(payload),
                meta["parse_status"],
                meta["latency_ms"],
            ),
        )
        audit(conn, f"agent:{role}", "assess", "incident", inc_id, json.dumps({"model": meta["model"], "parse": meta["parse_status"]}))

    cmp = result["comparison"]
    # union of obligations so clocks start even when blocked
    by_id = {}
    for o in (result["analyst"].get("obligations") or []) + (result["verifier"].get("obligations") or []):
        if o.get("clause_id"):
            by_id[o["clause_id"]] = o

    reportable = 1 if result["analyst"].get("reportable") or result["verifier"].get("reportable") else 0
    conn.execute(
        """INSERT INTO decisions (incident_id, reportable, flags, status)
           VALUES (?,?,?,?)""",
        (inc_id, reportable, json.dumps(cmp["flags"]), cmp["status"]),
    )
    audit(conn, "system", "decide", "incident", inc_id, json.dumps(cmp))

    clause_map = {c["clause_id"]: c for c in clauses}
    for cid, o in by_id.items():
        c = clause_map.get(cid)
        if not c:
            continue
        due = due_at(incident, c)
        conn.execute(
            """INSERT INTO obligations (incident_id, clause_id, authority, form, due_at, status)
               VALUES (?,?,?,?,?,'open')""",
            (inc_id, cid, o.get("authority") or c["authority"], o.get("form") or c["form"], due),
        )

    tags = result["analyst"].get("hazard_tags") or incident.get("hazard_tags") or []
    serious = bool(incident.get("fatality") or incident.get("hospitalised"))
    capa_days = 7 if serious else 30
    owner = f"EHS {site['name']}"
    capa_due = (datetime.now(IST) + timedelta(days=capa_days)).isoformat()
    for tag in tags:
        conn.execute(
            """INSERT INTO capa (incident_id, site_id, hazard_tag, action, owner, due_at, status)
               VALUES (?,?,?,?,?,?, 'open')""",
            (
                inc_id,
                site["site_id"],
                tag,
                f"Eliminate or control hazard `{tag}` at {site['name']}",
                owner,
                capa_due,
            ),
        )

    conn.execute("UPDATE incidents SET status=? WHERE incident_id=?", (cmp["status"], inc_id))
    conn.commit()
    decision = conn.execute(
        "SELECT * FROM decisions WHERE incident_id=? ORDER BY decision_id DESC LIMIT 1",
        (inc_id,),
    ).fetchone()
    return {"comparison": cmp, "decision_id": decision["decision_id"]}


class Engine:
    def __init__(self, regulations: dict, incidents_seed: list[dict]):
        self.clauses = flatten_clauses(regulations)
        self.clause_by_id = {c["clause_id"]: c for c in self.clauses}
        self.retriever = Retriever(self.clauses, incidents_seed)

    def retrieve_for(self, incident: dict, site: dict) -> list[dict]:
        query = (
            f"{incident['raw_text']} {site['type']} "
            + " ".join(incident.get("hazard_tags") or [])
        )
        tfidf = self.retriever.regulations(query, site_type=site["type"], k=8)
        boosted = keyword_boost(incident["raw_text"], self.clauses)
        # keep only clauses whose site_types include this site, plus ESI/EC
        pool = [
            c
            for c in self.clauses
            if site["type"] in (c.get("site_types") or [])
        ]
        hits = merge_retrieval(tfidf, boosted, {c["clause_id"]: c for c in pool} or self.clause_by_id)
        if not hits:
            hits = tfidf
        return hits

    def run(self, conn, incident: dict, site: dict) -> dict:
        retrieved = self.retrieve_for(incident, site)
        result = assess_incident(incident, site, retrieved)
        persisted = persist_assessment(conn, incident, site, self.clauses, result)
        return {**result, **persisted, "retrieved": [c["clause_id"] for c in retrieved]}
