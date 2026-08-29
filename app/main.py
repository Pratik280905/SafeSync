from __future__ import annotations

import json
import os
from datetime import datetime
from uuid import uuid4

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.clocks import IST, clock_state
from app.correlate import hazard_clusters, hazard_detail
from app.db import audit, connect, db_path, row_to_dict, rows_to_dicts
from app.filing import FilingBlocked, submit as filing_submit
from app.workflow import Engine

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def ensure_db() -> None:
    path = db_path()
    if path.exists() and path.stat().st_size > 2000:
        return
    import sys

    sys.path.insert(0, str(ROOT))
    from scripts.seed_db import main as seed

    seed()


app = FastAPI(title="SafeSync")


@app.on_event("startup")
def _startup() -> None:
    ensure_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        regs = json.loads((root / "data" / "regulations.json").read_text(encoding="utf-8"))
        incs = json.loads((root / "data" / "incidents.json").read_text(encoding="utf-8"))
        _engine = Engine(regs, incs)
    return _engine


class NoteBody(BaseModel):
    approver: str
    note: str


class CloseBody(BaseModel):
    evidence: str
    actor: str = "ehs_lead"


class NewIncident(BaseModel):
    site_id: str
    raw_text: str
    reported_by: str = "supervisor"
    channel: str = "app"
    fatality: bool = False
    hospitalised: bool = False
    near_miss: bool = False
    days_lost_est: int = 0
    hazard_tags: list[str] = []


@app.get("/api/health")
def health():
    return {"ok": True, "db": str(db_path())}


@app.get("/api/summary")
def summary():
    conn = connect()
    now = datetime.now(IST)
    open_ob = conn.execute("SELECT due_at FROM obligations WHERE status='open'").fetchall()
    missed = 0
    for o in open_ob:
        st, _ = clock_state(o["due_at"], now)
        if st == "missed":
            missed += 1
    blocked = conn.execute(
        """SELECT COUNT(*) FROM decisions d
           WHERE d.status='blocked' AND d.decision_id IN
           (SELECT MAX(decision_id) FROM decisions GROUP BY incident_id)"""
    ).fetchone()[0]
    ready = conn.execute(
        """SELECT COUNT(*) FROM decisions d
           WHERE d.status='ready_for_approval' AND d.decision_id IN
           (SELECT MAX(decision_id) FROM decisions GROUP BY incident_id)"""
    ).fetchone()[0]
    out = {
        "sites": conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0],
        "incidents": conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0],
        "open_clocks": len(open_ob),
        "missed": missed,
        "blocked": blocked,
        "ready": ready,
    }
    conn.close()
    return out


@app.get("/api/clock-board")
def clock_board():
    conn = connect()
    obls = conn.execute(
        """
        SELECT o.*, i.raw_text, i.site_id, i.status AS incident_status,
               s.name AS site_name, c.citation, c.heading
        FROM obligations o
        JOIN incidents i ON i.incident_id = o.incident_id
        JOIN sites s ON s.site_id = i.site_id
        JOIN clauses c ON c.clause_id = o.clause_id
        WHERE o.status = 'open'
        """
    ).fetchall()
    now = datetime.now(IST)
    cards = []
    for o in obls:
        state, remaining = clock_state(o["due_at"], now)
        cards.append(
            {
                **dict(o),
                "clock_state": state,
                "hours_remaining": remaining,
                "one_liner": (o["raw_text"] or "")[:140],
            }
        )
    cards.sort(key=lambda x: x["hours_remaining"])
    capa_open = conn.execute("SELECT COUNT(*) FROM capa WHERE status IN ('open','in_progress')").fetchone()[0]
    capa_overdue = conn.execute(
        "SELECT COUNT(*) FROM capa WHERE status != 'closed' AND due_at < datetime('now')"
    ).fetchone()[0]
    conn.close()
    return {"cards": cards, "capa": {"open": capa_open, "overdue": capa_overdue}}


@app.get("/api/incidents")
def list_incidents(status: str | None = None):
    conn = connect()
    if status:
        rows = conn.execute(
            """SELECT i.*, s.name AS site_name, s.type AS site_type
               FROM incidents i JOIN sites s ON s.site_id = i.site_id
               WHERE i.status=? ORDER BY i.occurred_at DESC""",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT i.*, s.name AS site_name, s.type AS site_type
               FROM incidents i JOIN sites s ON s.site_id = i.site_id
               ORDER BY i.occurred_at DESC"""
        ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.get("/api/incidents/{incident_id}")
def incident_detail(incident_id: str):
    conn = connect()
    inc = conn.execute(
        """SELECT i.*, s.name AS site_name, s.type AS site_type, s.jurisdictions, s.occupier
           FROM incidents i JOIN sites s ON s.site_id = i.site_id
           WHERE i.incident_id=?""",
        (incident_id,),
    ).fetchone()
    if not inc:
        conn.close()
        raise HTTPException(404, "incident not found")
    assessments = conn.execute(
        "SELECT * FROM assessments WHERE incident_id=? ORDER BY created_at",
        (incident_id,),
    ).fetchall()
    decision = conn.execute(
        "SELECT * FROM decisions WHERE incident_id=? ORDER BY decision_id DESC LIMIT 1",
        (incident_id,),
    ).fetchone()
    obligations = conn.execute(
        """SELECT o.*, c.citation, c.heading, c.text, c.source_pdf, c.source_page, c.verified
           FROM obligations o JOIN clauses c ON c.clause_id = o.clause_id
           WHERE o.incident_id=?""",
        (incident_id,),
    ).fetchall()
    filings = conn.execute("SELECT * FROM filings WHERE incident_id=? ORDER BY filed_at", (incident_id,)).fetchall()
    capas = conn.execute("SELECT * FROM capa WHERE incident_id=?", (incident_id,)).fetchall()
    audit_rows = conn.execute(
        "SELECT * FROM audit_log WHERE entity_id=? ORDER BY audit_id",
        (incident_id,),
    ).fetchall()
    hazards = conn.execute(
        "SELECT hazard_tag FROM incident_hazards WHERE incident_id=?",
        (incident_id,),
    ).fetchall()
    conn.close()
    parsed_assess = []
    for a in assessments:
        d = dict(a)
        try:
            d["payload"] = json.loads(d["payload"])
        except Exception:
            pass
        parsed_assess.append(d)
    dec = dict(decision) if decision else None
    if dec and isinstance(dec.get("flags"), str):
        dec["flags"] = json.loads(dec["flags"])
    return {
        "incident": dict(inc),
        "assessments": parsed_assess,
        "decision": dec,
        "obligations": [dict(o) for o in obligations],
        "filings": [dict(f) for f in filings],
        "capa": [dict(c) for c in capas],
        "audit": [dict(a) for a in audit_rows],
        "hazards": [h["hazard_tag"] for h in hazards],
    }


@app.get("/api/queue")
def queue():
    conn = connect()
    rows = conn.execute(
        """
        SELECT d.*, i.raw_text, i.site_id, s.name AS site_name, s.type AS site_type
        FROM decisions d
        JOIN incidents i ON i.incident_id = d.incident_id
        JOIN sites s ON s.site_id = i.site_id
        WHERE d.status IN ('blocked','ready_for_approval')
          AND d.decision_id IN (SELECT MAX(decision_id) FROM decisions GROUP BY incident_id)
        ORDER BY d.created_at DESC
        """
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["flags"] = json.loads(item["flags"]) if isinstance(item["flags"], str) else item["flags"]
        assessments = conn.execute(
            "SELECT agent_role, payload, model, confidence, reportable FROM assessments WHERE incident_id=?",
            (r["incident_id"],),
        ).fetchall()
        sides = {}
        for a in assessments:
            p = json.loads(a["payload"])
            sides[a["agent_role"]] = p
        item["analyst"] = sides.get("analyst")
        item["verifier"] = sides.get("verifier")
        out.append(item)
    conn.close()
    return {"blocked": [x for x in out if x["status"] == "blocked"], "ready": [x for x in out if x["status"] == "ready_for_approval"]}


@app.post("/api/decisions/{decision_id}/approve")
def approve(decision_id: int, body: NoteBody):
    if not body.note.strip():
        raise HTTPException(400, "note is required")
    conn = connect()
    d = conn.execute("SELECT * FROM decisions WHERE decision_id=?", (decision_id,)).fetchone()
    if not d:
        conn.close()
        raise HTTPException(404, "decision not found")
    now = datetime.now(IST).isoformat()
    conn.execute(
        "UPDATE decisions SET status='approved', approved_by=?, approved_at=?, approver_note=? WHERE decision_id=?",
        (body.approver, now, body.note, decision_id),
    )
    conn.execute("UPDATE incidents SET status='approved' WHERE incident_id=?", (d["incident_id"],))
    audit(conn, f"user:{body.approver}", "approve", "incident", d["incident_id"], body.note)
    conn.commit()
    conn.close()
    return {"ok": True, "status": "approved"}


@app.post("/api/decisions/{decision_id}/reject")
def reject(decision_id: int, body: NoteBody):
    if not body.note.strip():
        raise HTTPException(400, "note is required")
    conn = connect()
    d = conn.execute("SELECT * FROM decisions WHERE decision_id=?", (decision_id,)).fetchone()
    if not d:
        conn.close()
        raise HTTPException(404, "decision not found")
    now = datetime.now(IST).isoformat()
    conn.execute(
        "UPDATE decisions SET status='rejected', approved_by=?, approved_at=?, approver_note=? WHERE decision_id=?",
        (body.approver, now, body.note, decision_id),
    )
    conn.execute("UPDATE incidents SET status='rejected' WHERE incident_id=?", (d["incident_id"],))
    audit(conn, f"user:{body.approver}", "reject", "incident", d["incident_id"], body.note)
    conn.commit()
    conn.close()
    return {"ok": True, "status": "rejected"}


@app.post("/api/obligations/{obligation_id}/file")
def file_obligation(obligation_id: int, body: NoteBody):
    conn = connect()
    try:
        result = filing_submit(conn, obligation_id, body.approver)
    except FilingBlocked as e:
        conn.close()
        raise HTTPException(409, str(e))
    conn.close()
    return result


@app.get("/api/hazards")
def hazards():
    conn = connect()
    data = hazard_clusters(conn)
    conn.close()
    return data


@app.get("/api/hazards/{tag}")
def hazard(tag: str):
    conn = connect()
    data = hazard_detail(conn, tag)
    conn.close()
    return data


@app.post("/api/capa/{capa_id}/close")
def close_capa(capa_id: int, body: CloseBody):
    conn = connect()
    row = conn.execute("SELECT * FROM capa WHERE capa_id=?", (capa_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "capa not found")
    now = datetime.now(IST).isoformat()
    conn.execute(
        "UPDATE capa SET status='closed', closed_at=?, evidence=? WHERE capa_id=?",
        (now, body.evidence, capa_id),
    )
    audit(conn, f"user:{body.actor}", "capa_close", "capa", str(capa_id), body.evidence)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/incidents")
def create_incident(body: NewIncident):
    conn = connect()
    site = conn.execute("SELECT * FROM sites WHERE site_id=?", (body.site_id,)).fetchone()
    if not site:
        conn.close()
        raise HTTPException(400, "unknown site")
    now = datetime.now(IST)
    incident_id = f"INC-{uuid4().hex[:6].upper()}"
    incident = {
        "incident_id": incident_id,
        "site_id": body.site_id,
        "occurred_at": now.isoformat(),
        "reported_at": now.isoformat(),
        "reported_by": body.reported_by,
        "channel": body.channel,
        "raw_text": body.raw_text,
        "fatality": 1 if body.fatality else 0,
        "hospitalised": 1 if body.hospitalised else 0,
        "days_lost_est": body.days_lost_est,
        "persons_affected": 1,
        "control_present": 0,
        "near_miss": 1 if body.near_miss else 0,
        "hazard_tags": body.hazard_tags,
        "bucket": "live",
    }
    conn.execute(
        """INSERT INTO incidents (incident_id, site_id, occurred_at, reported_at, reported_by, channel,
           raw_text, fatality, hospitalised, days_lost_est, persons_affected, control_present, near_miss, bucket, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')""",
        (
            incident_id,
            body.site_id,
            incident["occurred_at"],
            incident["reported_at"],
            body.reported_by,
            body.channel,
            body.raw_text,
            incident["fatality"],
            incident["hospitalised"],
            body.days_lost_est,
            1,
            0,
            incident["near_miss"],
            "live",
        ),
    )
    for tag in body.hazard_tags:
        conn.execute(
            "INSERT INTO incident_hazards (incident_id, hazard_tag, occurred_at, site_id) VALUES (?,?,?,?)",
            (incident_id, tag, incident["occurred_at"], body.site_id),
        )
    audit(conn, f"user:{body.reported_by}", "intake", "incident", incident_id, body.raw_text[:200])
    conn.commit()
    site_d = dict(site)
    try:
        site_d["jurisdictions"] = json.loads(site_d["jurisdictions"])
    except Exception:
        pass
    out = get_engine().run(conn, incident, site_d)
    conn.close()
    return {"incident_id": incident_id, **{k: out[k] for k in ("comparison", "decision_id", "retrieved") if k in out}}


@app.get("/api/sites")
def sites():
    conn = connect()
    rows = conn.execute("SELECT * FROM sites ORDER BY name").fetchall()
    conn.close()
    return rows_to_dicts(rows)


@app.post("/regulator/{authority}/submit")
def regulator_submit(authority: str, body: dict):
    ref = f"{authority[:4].upper()}-{uuid4().hex[:8].upper()}"
    return {"status": "accepted", "reference_no": ref, "received_at": datetime.now(IST).isoformat()}


UI_DIST = ROOT / "ui" / "dist"
if (UI_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST / "assets")), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api") or full_path.startswith("regulator"):
        raise HTTPException(404)
    index = UI_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "message": "UI not built yet. Run: cd ui && npm install && npm run build. Dev: npm run dev on port 5173.",
        "health": "/api/health",
    }
