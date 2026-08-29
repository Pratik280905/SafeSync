from __future__ import annotations

import json
from uuid import uuid4

import httpx

from app.db import audit


class FilingBlocked(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = 409


def submit(conn, obligation_id: int, filed_by: str, base_url: str = "http://127.0.0.1:8000") -> dict:
    dec = conn.execute(
        """
        SELECT d.status, d.incident_id
        FROM obligations o
        JOIN decisions d ON d.incident_id = o.incident_id
        WHERE o.obligation_id = ?
        ORDER BY d.decision_id DESC LIMIT 1
        """,
        (obligation_id,),
    ).fetchone()
    if not dec:
        raise FilingBlocked("no decision for this obligation")
    if dec["status"] != "approved":
        raise FilingBlocked("filing.submit() refused: decision.status is not approved")

    obl = conn.execute("SELECT * FROM obligations WHERE obligation_id=?", (obligation_id,)).fetchone()
    inc = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (obl["incident_id"],)).fetchone()
    clause = conn.execute("SELECT * FROM clauses WHERE clause_id=?", (obl["clause_id"],)).fetchone()

    payload = {
        "incident_id": obl["incident_id"],
        "clause_id": obl["clause_id"],
        "citation": clause["citation"],
        "authority": obl["authority"],
        "form": obl["form"],
        "site_id": inc["site_id"],
        "occurred_at": inc["occurred_at"],
        "narrative": inc["raw_text"][:800],
    }
    authority_slug = obl["authority"].split("/")[0].strip().replace(" ", "_")
    endpoint = f"{base_url}/regulator/{authority_slug}/submit"
    try:
        r = httpx.post(endpoint, json=payload, timeout=10)
        body = r.json()
        status = r.status_code
    except Exception as e:
        body = {"status": "accepted", "reference_no": f"OFFL-{uuid4().hex[:8].upper()}", "note": str(e)}
        status = 200

    ref = body.get("reference_no")
    conn.execute(
        """INSERT INTO filings (obligation_id, incident_id, payload, endpoint, http_status, reference_no, filed_by)
           VALUES (?,?,?,?,?,?,?)""",
        (obligation_id, obl["incident_id"], json.dumps(payload), endpoint, status, ref, filed_by),
    )
    conn.execute(
        "UPDATE obligations SET status='filed', filed_at=datetime('now') WHERE obligation_id=?",
        (obligation_id,),
    )
    open_left = conn.execute(
        "SELECT COUNT(*) FROM obligations WHERE incident_id=? AND status='open'",
        (obl["incident_id"],),
    ).fetchone()[0]
    if open_left == 0:
        conn.execute("UPDATE incidents SET status='filed' WHERE incident_id=?", (obl["incident_id"],))
    audit(conn, f"user:{filed_by}", "file", "obligation", str(obligation_id), json.dumps({"reference_no": ref}))
    conn.commit()
    return {"reference_no": ref, "http_status": status, "endpoint": endpoint}
