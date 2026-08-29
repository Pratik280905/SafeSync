from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)

ANALYST_INSTRUCTIONS = """You are a compliance analyst for industrial and construction safety in India.

You will be given: (a) an incident report as written in the field, (b) the site's
type and the acts it is registered under, (c) the full text of candidate statutory
clauses retrieved from the regulation store.

Decide which clauses, if any, create a reporting obligation for this incident.

Hard rules:
- Use ONLY the clauses provided. Never cite a clause that is not in the Documents section.
- Every obligation you return must quote the clause_id exactly as given.
- Take window_hours and clock_starts from the clause. Do not infer a deadline.
- If a fact you need is absent from the report, do not assume it. Set escalate to
  true and name the missing fact. Escalating is the correct answer when the report
  is incomplete.
- Return ONLY a JSON object matching the schema. No preamble, no markdown fences.
"""

VERIFIER_INSTRUCTIONS = """You are an independent compliance verifier. You are given an incident report, the
statutory clauses retrieved for it, and a determination made by another analyst.

Independently decide the correct answer from the incident and the clauses. Then
state whether you agree with the determination.

Do not defer to the analyst. If the analyst cited a clause whose trigger conditions
are not met by the facts in the report, say so and give the clause_id.
Return ONLY the JSON object, in the same schema, plus:
  "agrees_with_analyst": true|false,
  "disagreement_notes": "..."
"""

SCHEMA_HINT = {
    "incident_id": "INC-0000",
    "reportable": True,
    "confidence": 0.86,
    "site_type": "factory",
    "obligations": [
        {
            "clause_id": "FA-88",
            "authority": "DISH Maharashtra",
            "form": "prescribed form under state rules",
            "window_hours": 24,
            "clock_starts": "occurrence",
            "reason": "Injury prevented the worker from working for more than 48 hours.",
        }
    ],
    "severity": "serious",
    "hazard_tags": ["conveyor_nip_point"],
    "missing_information": [],
    "escalate": False,
    "escalation_reason": None,
}


def parse_agent_json(text: str, valid_clause_ids: set[str], require_agree: bool = False) -> dict:
    raw = (text or "").strip()
    m = FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no json object in response")
    obj = json.loads(raw[start : end + 1])

    for k in ("incident_id", "reportable", "confidence", "obligations", "escalate"):
        if k not in obj:
            raise ValueError(f"missing key: {k}")

    if not isinstance(obj["obligations"], list):
        raise ValueError("obligations must be a list")

    bad = [o.get("clause_id") for o in obj["obligations"] if o.get("clause_id") not in valid_clause_ids]
    if bad:
        raise ValueError(f"hallucinated clause ids: {bad}")

    obj["reportable"] = bool(obj["reportable"])
    obj["escalate"] = bool(obj["escalate"])
    obj["confidence"] = float(obj["confidence"])
    if require_agree and "agrees_with_analyst" not in obj:
        obj["agrees_with_analyst"] = True
    return obj


def blind_analyst(analyst: dict) -> dict:
    blinded = {
        "incident_id": analyst.get("incident_id"),
        "reportable": analyst.get("reportable"),
        "site_type": analyst.get("site_type"),
        "obligations": [
            {k: o.get(k) for k in ("clause_id", "authority", "form", "window_hours", "clock_starts")}
            for o in analyst.get("obligations") or []
        ],
        "escalate": analyst.get("escalate"),
        "hazard_tags": analyst.get("hazard_tags"),
    }
    return blinded


def compare(analyst: dict, verifier: dict) -> dict:
    flags = []
    if analyst["reportable"] != verifier["reportable"]:
        flags.append("REPORTABLE_MISMATCH")

    a = {o["clause_id"] for o in analyst["obligations"]}
    v = {o["clause_id"] for o in verifier["obligations"]}
    if a != v:
        flags.append("CLAUSE_SET_MISMATCH")

    a_w = {(o["clause_id"], o.get("window_hours")) for o in analyst["obligations"]}
    v_w = {(o["clause_id"], o.get("window_hours")) for o in verifier["obligations"]}
    if a_w & v_w != a_w | v_w and "CLAUSE_SET_MISMATCH" not in flags:
        flags.append("DEADLINE_MISMATCH")

    if verifier.get("agrees_with_analyst") is False:
        flags.append("VERIFIER_OBJECTION")

    try:
        low_conf = min(float(analyst["confidence"]), float(verifier["confidence"])) < 0.70
    except (TypeError, ValueError, KeyError):
        low_conf = True
    if low_conf:
        flags.append("LOW_CONFIDENCE")

    if analyst.get("escalate") or verifier.get("escalate"):
        flags.append("MISSING_INFORMATION")

    blocked = bool(flags)
    return {"flags": flags, "status": "blocked" if blocked else "ready_for_approval"}


def _clause_block(clauses: list[dict]) -> str:
    parts = []
    for c in clauses:
        parts.append(
            f"clause_id: {c['clause_id']}\n"
            f"citation: {c['citation']}\n"
            f"heading: {c['heading']}\n"
            f"authority: {c['authority']}\n"
            f"form: {c['form']}\n"
            f"window_hours: {c['window_hours']}\n"
            f"clock_starts: {c['clock_starts']}\n"
            f"site_types: {c.get('site_types')}\n"
            f"text: {c['text']}\n"
        )
    return "\n---\n".join(parts)


def build_analyst_prompt(incident: dict, site: dict, clauses: list[dict]) -> str:
    return (
        f"{ANALYST_INSTRUCTIONS}\n\n"
        f"JSON schema example:\n{json.dumps(SCHEMA_HINT, indent=2)}\n\n"
        f"### Site\n"
        f"site_id: {site['site_id']}\nname: {site['name']}\ntype: {site['type']}\n"
        f"jurisdictions: {site.get('jurisdictions')}\n\n"
        f"### Incident\n"
        f"incident_id: {incident['incident_id']}\n"
        f"occurred_at: {incident.get('occurred_at')}\n"
        f"raw_text: {incident['raw_text']}\n"
        f"fatality: {incident.get('fatality')}\n"
        f"hospitalised: {incident.get('hospitalised')}\n"
        f"days_lost_estimate: {incident.get('days_lost_est', incident.get('days_lost_estimate'))}\n"
        f"near_miss: {incident.get('near_miss')}\n\n"
        f"### Documents (retrieved clauses — cite ONLY these clause_ids)\n"
        f"{_clause_block(clauses)}\n"
    )


def build_verifier_prompt(incident: dict, site: dict, clauses: list[dict], blinded: dict) -> str:
    return (
        f"{VERIFIER_INSTRUCTIONS}\n\n"
        f"JSON schema example:\n{json.dumps({**SCHEMA_HINT, 'agrees_with_analyst': True, 'disagreement_notes': None}, indent=2)}\n\n"
        f"### Site\n"
        f"site_id: {site['site_id']}\nname: {site['name']}\ntype: {site['type']}\n\n"
        f"### Incident\nincident_id: {incident['incident_id']}\nraw_text: {incident['raw_text']}\n\n"
        f"### Analyst determination (confidence and reasons STRIPPED)\n"
        f"{json.dumps(blinded, indent=2)}\n\n"
        f"### Documents\n{_clause_block(clauses)}\n"
    )


def groq_key() -> str:
    return (os.environ.get("GROQ_API_KEY") or os.environ.get("ROCKETRIDE_GROQ_KEY") or "").strip()


def groq_complete(prompt: str, model: str) -> str:
    from groq import Groq

    client = Groq(api_key=groq_key())
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": "Return only a JSON object."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


def run_agent_with_repair(prompt: str, model: str, valid_ids: set[str], require_agree: bool = False) -> tuple[dict, str, int]:
    t0 = time.time()
    text = groq_complete(prompt, model)
    status = "ok"
    try:
        obj = parse_agent_json(text, valid_ids, require_agree=require_agree)
    except Exception as err:
        repair = prompt + f"\n\nYour previous response was invalid: {err}. Return only the corrected JSON object."
        text = groq_complete(repair, model)
        status = "repaired"
        try:
            obj = parse_agent_json(text, valid_ids, require_agree=require_agree)
        except Exception:
            obj = {
                "incident_id": "",
                "reportable": False,
                "confidence": 0.0,
                "obligations": [],
                "escalate": True,
                "escalation_reason": "parse_failed",
                "missing_information": ["model_output_unparseable"],
                "hazard_tags": [],
                "severity": "unknown",
            }
            status = "parse_failed"
    ms = int((time.time() - t0) * 1000)
    return obj, status, ms


# --- heuristic fallback so the demo never dies without Groq ---

def heuristic_assess(incident: dict, site: dict, clauses: list[dict], role: str) -> dict:
    text = (incident.get("raw_text") or "").lower()
    site_type = site["type"]
    fatality = bool(incident.get("fatality"))
    hospitalised = bool(incident.get("hospitalised"))
    days = int(incident.get("days_lost_est") or incident.get("days_lost_estimate") or 0)
    near = bool(incident.get("near_miss"))
    bucket = incident.get("bucket") or ""
    valid = {c["clause_id"]: c for c in clauses}

    def take(*ids):
        obs = []
        for cid in ids:
            c = valid.get(cid)
            if not c:
                continue
            obs.append(
                {
                    "clause_id": cid,
                    "authority": c["authority"],
                    "form": c["form"],
                    "window_hours": c["window_hours"],
                    "clock_starts": c["clock_starts"],
                    "reason": f"Trigger matched for {c['citation']}.",
                }
            )
        return obs

    escalate = False
    missing = []
    reportable = False
    obligations: list[dict] = []
    severity = "minor"
    conf = 0.88

    if bucket == "garbled" or (not text or "not sure" in text and "battery" in text):
        escalate = True
        missing = ["injury outcome", "whether person was hospitalised", "site location confirmation"]
        conf = 0.35
        severity = "unknown"
    elif "silicosis" in text or "hearing loss" in text or "occupational disease" in text or bucket == "occupational_disease":
        reportable = True
        severity = "occupational_disease"
        if site_type == "factory":
            obligations = take("FA-89")
        else:
            obligations = take("BOCW-R223")
    elif bucket == "dangerous_occurrence" or any(w in text for w in ["fire", "explosion", "collapse of", "sprinkler"]):
        reportable = True
        severity = "dangerous_occurrence"
        if site_type == "factory":
            obligations = take("FA-88A", "MH-R104")
        else:
            obligations = take("BOCW-39")
    elif fatality:
        reportable = True
        severity = "fatal"
        conf = 0.95
        if site_type == "factory":
            obligations = take("FA-88", "MH-R103", "ESI-ACC-REPORT", "EC-10B")
        else:
            obligations = take("BOCW-39", "BOCW-R210", "ESI-ACC-REPORT", "EC-10B")
    elif hospitalised or days >= 2:
        reportable = True
        severity = "serious"
        if site_type == "factory":
            obligations = take("FA-88", "MH-R103", "ESI-ACC-REPORT", "EC-10B")
        else:
            obligations = take("BOCW-39", "BOCW-R210", "ESI-ACC-REPORT", "EC-10B")
    elif near:
        reportable = False
        severity = "near_miss"
        conf = 0.84
        obligations = []
    else:
        reportable = False
        obligations = []

    if bucket == "ambiguous":
        escalate = True
        missing = ["exact duration of incapacity not confirmed"]
        conf = 0.52
        # analyst leans reportable, verifier does not — designed disagreement
        if role == "analyst":
            reportable = True
            if site_type == "factory":
                obligations = take("FA-88", "ESI-ACC-REPORT")
            else:
                obligations = take("BOCW-39", "ESI-ACC-REPORT")
        else:
            reportable = False
            obligations = []
            conf = 0.61

    out = {
        "incident_id": incident["incident_id"],
        "reportable": reportable,
        "confidence": conf,
        "site_type": site_type,
        "obligations": obligations,
        "severity": severity,
        "hazard_tags": incident.get("hazard_tags") or [],
        "missing_information": missing,
        "escalate": escalate,
        "escalation_reason": missing[0] if missing else None,
    }
    if role == "verifier":
        if bucket == "ambiguous":
            out["agrees_with_analyst"] = False
            out["disagreement_notes"] = "48-hour incapacity threshold is not established by the facts."
        else:
            out["agrees_with_analyst"] = True
            out["disagreement_notes"] = None
    return out


def use_llm() -> bool:
    return os.environ.get("SAFESYNC_USE_LLM", "1") not in ("0", "false", "False") and bool(groq_key())


ANALYST_MODELS = [
    os.environ.get("GROQ_ANALYST_MODEL", "openai/gpt-oss-120b"),
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
VERIFIER_MODELS = [
    os.environ.get("GROQ_VERIFIER_MODEL", "openai/gpt-oss-20b"),
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
]


def _first_working(models: list[str], prompt: str, valid: set[str], require_agree: bool) -> tuple[dict, str, int, str]:
    last_err = None
    for model in models:
        if not model:
            continue
        try:
            obj, status, ms = run_agent_with_repair(prompt, model, valid, require_agree=require_agree)
            obj["_model"] = model
            return obj, status, ms, model
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"all models failed: {last_err}")


def assess_incident(incident: dict, site: dict, clauses: list[dict]) -> dict:
    valid = {c["clause_id"] for c in clauses}
    if not use_llm():
        a = heuristic_assess(incident, site, clauses, "analyst")
        v = heuristic_assess(incident, site, clauses, "verifier")
        return {
            "analyst": a,
            "verifier": v,
            "analyst_meta": {"model": "heuristic", "parse_status": "ok", "latency_ms": 1},
            "verifier_meta": {"model": "heuristic", "parse_status": "ok", "latency_ms": 1},
            "comparison": compare(a, v),
        }

    a_prompt = build_analyst_prompt(incident, site, clauses)
    try:
        a, a_stat, a_ms, a_model = _first_working(ANALYST_MODELS, a_prompt, valid, False)
    except Exception:
        a = heuristic_assess(incident, site, clauses, "analyst")
        a_stat, a_ms, a_model = "heuristic_fallback", 0, "heuristic"

    blinded = blind_analyst(a)
    v_prompt = build_verifier_prompt(incident, site, clauses, blinded)
    try:
        v, v_stat, v_ms, v_model = _first_working(VERIFIER_MODELS, v_prompt, valid, True)
    except Exception:
        v = heuristic_assess(incident, site, clauses, "verifier")
        v_stat, v_ms, v_model = "heuristic_fallback", 0, "heuristic"

    return {
        "analyst": a,
        "verifier": v,
        "analyst_meta": {"model": a.get("_model", a_model), "parse_status": a_stat, "latency_ms": a_ms},
        "verifier_meta": {"model": v.get("_model", v_model), "parse_status": v_stat, "latency_ms": v_ms},
        "comparison": compare(a, v),
    }
