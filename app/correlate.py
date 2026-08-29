from __future__ import annotations

from collections import defaultdict


def hazard_clusters(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT hazard_tag,
               COUNT(DISTINCT site_id) AS sites,
               COUNT(*) AS events
        FROM incident_hazards
        WHERE occurred_at >= datetime('now', '-90 day')
        GROUP BY hazard_tag
        HAVING sites >= 2
        ORDER BY events DESC
        """
    ).fetchall()
    clusters = []
    for r in rows:
        tag = r["hazard_tag"]
        per = conn.execute(
            """
            SELECT i.site_id, s.name AS site_name,
                   MAX(i.occurred_at) AS last_seen,
                   SUM(CASE WHEN i.control_present = 0 THEN 1 ELSE 0 END) AS uncontrolled,
                   COUNT(*) AS n
            FROM incidents i
            JOIN incident_hazards h ON h.incident_id = i.incident_id
            JOIN sites s ON s.site_id = i.site_id
            WHERE h.hazard_tag = ?
            GROUP BY i.site_id
            """,
            (tag,),
        ).fetchall()
        overdue = conn.execute(
            """
            SELECT COUNT(*) FROM capa
            WHERE hazard_tag = ? AND status IN ('open','overdue')
              AND due_at < datetime('now')
            """,
            (tag,),
        ).fetchone()[0]
        uncontrolled = sum(p["uncontrolled"] or 0 for p in per)
        score = r["events"] * 2 + r["sites"] * 5 + uncontrolled * 3 + overdue * 4
        clusters.append(
            {
                "hazard_tag": tag,
                "sites": r["sites"],
                "events": r["events"],
                "uncontrolled": uncontrolled,
                "overdue_capa": overdue,
                "score": score,
                "site_rows": [dict(p) for p in per],
            }
        )
    clusters.sort(key=lambda x: -x["score"])
    return clusters


def hazard_detail(conn, tag: str) -> dict:
    clusters = {c["hazard_tag"]: c for c in hazard_clusters(conn)}
    base = clusters.get(tag) or {"hazard_tag": tag, "sites": 0, "events": 0, "uncontrolled": 0, "score": 0, "site_rows": []}
    incidents = conn.execute(
        """
        SELECT i.incident_id, i.site_id, s.name AS site_name, i.occurred_at, i.near_miss,
               i.fatality, i.hospitalised, i.status, i.raw_text, i.control_present
        FROM incidents i
        JOIN incident_hazards h ON h.incident_id = i.incident_id
        JOIN sites s ON s.site_id = i.site_id
        WHERE h.hazard_tag = ?
        ORDER BY i.occurred_at DESC
        """,
        (tag,),
    ).fetchall()
    capas = conn.execute(
        "SELECT * FROM capa WHERE hazard_tag = ? ORDER BY due_at",
        (tag,),
    ).fetchall()
    return {
        **base,
        "incidents": [dict(i) for i in incidents],
        "capa": [dict(c) for c in capas],
        "headline": (
            f"`{tag}` — present at {base.get('sites', 0)} of 12 sites, "
            f"control recorded on a minority of events, {base.get('overdue_capa', 0)} overdue CAPAs."
        ),
    }
