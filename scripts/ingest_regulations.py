"""Ingest clauses into SQLite. Refuses unverified unless --allow-unverified."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connect, init_db
from app.retrieve import flatten_clauses


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--allow-unverified", action="store_true")
    p.add_argument("--regulations", default=str(ROOT / "data" / "regulations.json"))
    args = p.parse_args()
    regs = json.loads(Path(args.regulations).read_text(encoding="utf-8"))
    clauses = flatten_clauses(regs)
    bad = [c["clause_id"] for c in clauses if not c.get("verified")]
    if bad and not args.allow_unverified:
        raise SystemExit(f"refusing unverified clauses: {bad} (pass --allow-unverified)")
    conn = connect()
    try:
        conn.execute("SELECT 1 FROM clauses LIMIT 1")
    except Exception:
        init_db(conn)
    for c in clauses:
        conn.execute(
            """INSERT OR REPLACE INTO clauses
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
    conn.commit()
    print(f"ingested {len(clauses)} clauses")


if __name__ == "__main__":
    main()
