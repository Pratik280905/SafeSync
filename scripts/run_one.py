"""Single-incident CLI. Uses the Python engine (Groq or heuristic)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.db import connect
from app.workflow import Engine


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--incident", default="INC-0001")
    p.add_argument("--text", default="")
    args = p.parse_args()
    conn = connect()
    if args.text:
        print("echo:", args.text)
        return
    row = conn.execute("SELECT * FROM incidents WHERE incident_id=?", (args.incident,)).fetchone()
    if not row:
        raise SystemExit("seed the db first: python scripts/seed_db.py")
    site = conn.execute("SELECT * FROM sites WHERE site_id=?", (row["site_id"],)).fetchone()
    regs = json.loads((ROOT / "data" / "regulations.json").read_text(encoding="utf-8"))
    incs = json.loads((ROOT / "data" / "incidents.json").read_text(encoding="utf-8"))
    engine = Engine(regs, incs)
    incident = dict(row)
    incident["hazard_tags"] = [
        r["hazard_tag"]
        for r in conn.execute("SELECT hazard_tag FROM incident_hazards WHERE incident_id=?", (args.incident,)).fetchall()
    ]
    site_d = dict(site)
    site_d["jurisdictions"] = json.loads(site_d["jurisdictions"])
    result = engine.run(conn, incident, site_d)
    print(json.dumps({"comparison": result["comparison"], "retrieved": result["retrieved"], "analyst": result["analyst"], "verifier": result["verifier"]}, indent=2))


if __name__ == "__main__":
    main()
