from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import connect


def main() -> None:
    golden = json.loads((ROOT / "eval" / "golden.json").read_text(encoding="utf-8"))
    conn = connect()
    tp = fp = fn = 0
    clause_hits = clause_total = 0
    escalate_ok = escalate_n = 0

    for g in golden:
        a = conn.execute(
            "SELECT payload FROM assessments WHERE incident_id=? AND agent_role='analyst' ORDER BY assessment_id DESC LIMIT 1",
            (g["incident_id"],),
        ).fetchone()
        if not a:
            print("missing", g["incident_id"])
            continue
        payload = json.loads(a["payload"])
        pred = bool(payload.get("reportable"))
        exp = g.get("expected_reportable")
        if g.get("expect_escalate"):
            escalate_n += 1
            if payload.get("escalate"):
                escalate_ok += 1
            continue
        if exp is True:
            if pred:
                tp += 1
            else:
                fn += 1
        elif exp is False:
            if pred:
                fp += 1
            else:
                tp += 1  # true negative counted in a crude accuracy bucket
        cited = {o["clause_id"] for o in payload.get("obligations") or []}
        want = set(g.get("expected_clause_ids") or [])
        if want:
            clause_total += len(want)
            clause_hits += len(want & cited)

    precision_like = tp / (tp + fp) if (tp + fp) else 0
    print(f"reportable accuracy proxy  tp={tp} fp={fp} fn={fn}  precision={precision_like:.2f}")
    print(f"clause citation recall     {clause_hits}/{clause_total}")
    print(f"escalation rate (golden)   {escalate_ok}/{escalate_n}")


if __name__ == "__main__":
    main()
