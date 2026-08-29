"""Reset safesync.db and load sites, clauses, 40 incidents, heuristic assessments."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.clocks import IST
from app.db import audit, connect, db_path, init_db
from app.retrieve import flatten_clauses
from app.workflow import Engine, persist_assessment
from app.agents import heuristic_assess, compare


def load(name: str):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def main() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_incidents", ROOT / "scripts" / "generate_incidents.py"
    )
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    gen.main()

    path = db_path()
    if path.exists():
        path.unlink()
        print(f"removed {path}")

    conn = connect()
    init_db(conn)

    sites = load("sites.json")
    regs = load("regulations.json")
    incidents = load("incidents.json")
    clauses = flatten_clauses(regs)

    for s in sites:
        conn.execute(
            """INSERT INTO sites (site_id, name, type, state, district, jurisdictions, headcount, occupier)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                s["site_id"],
                s["name"],
                s["type"],
                s["state"],
                s["district"],
                json.dumps(s["jurisdiction"]),
                s.get("headcount"),
                s.get("occupier"),
            ),
        )

    unverified = [c["clause_id"] for c in clauses if not c.get("verified")]
    if unverified:
        print("WARNING unverified:", unverified)
    for c in clauses:
        conn.execute(
            """INSERT INTO clauses
               (clause_id, jurisdiction, citation, heading, authority, form, window_hours,
                clock_starts, source_pdf, source_page, verified, text, trigger_json, site_types)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c["clause_id"],
                c["jurisdiction"],
                c["citation"],
                c["heading"],
                c["authority"],
                c["form"],
                c["window_hours"],
                c["clock_starts"],
                c.get("source_pdf"),
                c.get("source_page"),
                1 if c.get("verified") else 0,
                c["text"],
                json.dumps(c.get("trigger")),
                json.dumps(c.get("site_types")),
            ),
        )

    now = datetime.now(IST)
    site_by = {s["site_id"]: s for s in sites}
    for row in incidents:
        occurred = now - timedelta(hours=float(row["hours_ago"]))
        reported = occurred + timedelta(hours=float(row["report_delay_hours"]))
        fatality = 1 if row["outcome"]["fatality"] else 0
        hosp = 1 if row["outcome"]["hospitalised"] else 0
        conn.execute(
            """INSERT INTO incidents (incident_id, site_id, occurred_at, reported_at, reported_by, channel,
               raw_text, fatality, hospitalised, days_lost_est, persons_affected, control_present, near_miss, bucket, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'new')""",
            (
                row["incident_id"],
                row["site_id"],
                occurred.isoformat(),
                reported.isoformat(),
                row.get("reported_by"),
                row.get("channel"),
                row["raw_text"],
                fatality,
                hosp,
                row["outcome"].get("days_lost_estimate") or 0,
                row["outcome"].get("persons_affected") or 1,
                1 if row.get("control_present") else 0,
                1 if row.get("near_miss") else 0,
                row.get("bucket"),
            ),
        )
        for tag in row.get("hazard_tags") or []:
            conn.execute(
                "INSERT INTO incident_hazards (incident_id, hazard_tag, occurred_at, site_id) VALUES (?,?,?,?)",
                (row["incident_id"], tag, occurred.isoformat(), row["site_id"]),
            )
        audit(conn, "system", "seed", "incident", row["incident_id"], row.get("bucket") or "")

    conn.commit()

    engine = Engine(regs, incidents)
    # Seed assessments with heuristic so the board is full even without Groq.
    # Live POST /api/incidents still calls Groq when a key is set.
    os.environ["SAFESYNC_USE_LLM"] = "0"

    for row in incidents:
        site = dict(site_by[row["site_id"]])
        site["jurisdictions"] = site["jurisdiction"]
        inc_row = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (row["incident_id"],)).fetchone()
        incident = dict(inc_row)
        incident["hazard_tags"] = row.get("hazard_tags") or []
        incident["bucket"] = row.get("bucket")
        incident["days_lost_estimate"] = incident["days_lost_est"]
        retrieved = engine.retrieve_for(incident, site)
        a = heuristic_assess(incident, site, retrieved, "analyst")
        v = heuristic_assess(incident, site, retrieved, "verifier")
        persist_assessment(
            conn,
            incident,
            site,
            clauses,
            {
                "analyst": a,
                "verifier": v,
                "analyst_meta": {"model": "heuristic", "parse_status": "ok", "latency_ms": 1},
                "verifier_meta": {"model": "heuristic", "parse_status": "ok", "latency_ms": 1},
                "comparison": compare(a, v),
            },
        )

    # Pre-approve and file one clean reportable so filing history has a reference number
    demo = conn.execute(
        "SELECT decision_id, incident_id FROM decisions WHERE incident_id='INC-0002' ORDER BY decision_id DESC LIMIT 1"
    ).fetchone()
    if demo:
        now_s = datetime.now(IST).isoformat()
        conn.execute(
            "UPDATE decisions SET status='approved', approved_by=?, approved_at=?, approver_note=? WHERE decision_id=?",
            ("Priyanka (EHS Lead)", now_s, "Form 24 pack reviewed. File DISH and ESIC.", demo["decision_id"]),
        )
        conn.execute("UPDATE incidents SET status='approved' WHERE incident_id='INC-0002'")
        audit(conn, "user:Priyanka (EHS Lead)", "approve", "incident", "INC-0002", "demo seed approval")
        conn.commit()
        from app.filing import submit

        obls = conn.execute(
            "SELECT obligation_id FROM obligations WHERE incident_id='INC-0002'"
        ).fetchall()
        for o in obls:
            try:
                submit(conn, o["obligation_id"], "Priyanka (EHS Lead)")
            except Exception as e:
                print("seed filing skipped:", e)

    conn.execute(
        "UPDATE incidents SET control_present=1 WHERE incident_id='INC-0028'"
    )
    conn.execute(
        "UPDATE capa SET due_at = datetime('now','-3 day'), status='overdue' WHERE hazard_tag='conveyor_nip_point' AND incident_id != 'INC-0001'"
    )
    conn.commit()

    n_inc = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    n_cl = conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]
    n_ob = conn.execute("SELECT COUNT(*) FROM obligations WHERE status='open'").fetchone()[0]
    tag = conn.execute(
        """SELECT hazard_tag, COUNT(DISTINCT site_id) AS sites
           FROM incident_hazards WHERE hazard_tag='conveyor_nip_point'"""
    ).fetchone()
    print(f"seeded {n_inc} incidents, {n_cl} clauses, {n_ob} open clocks")
    print(f"conveyor_nip_point sites: {tag['sites'] if tag else 0}")
    conn.close()


if __name__ == "__main__":
    main()
