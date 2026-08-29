import { useEffect, useMemo, useState } from "react";
import { get, post } from "./api.js";

const FLAG_LABELS = {
  REPORTABLE_MISMATCH: "The two AIs disagree: must this be reported?",
  CLAUSE_SET_MISMATCH: "They picked different laws",
  DEADLINE_MISMATCH: "They disagree on how much time you have",
  VERIFIER_OBJECTION: "The second AI rejected the first AI's answer",
  LOW_CONFIDENCE: "Neither AI is sure enough",
  MISSING_INFORMATION: "The report is incomplete — a person must decide",
};

const STEPS = [
  {
    n: 1,
    id: "clock",
    title: "A messy report arrives",
    body: "A supervisor sends a WhatsApp-style note. SafeSync does not wait for a clean form.",
  },
  {
    n: 2,
    id: "clock",
    title: "Legal clocks start",
    body: "Indian factory and construction law already says how many hours you have. Those hours come from the law file, not from the AI.",
  },
  {
    n: 3,
    id: "queue",
    title: "Two AIs check independently",
    body: "One AI classifies. A second, different model checks. They never see each other's confidence scores.",
  },
  {
    n: 4,
    id: "queue",
    title: "Disagreement blocks filing",
    body: "If they disagree, the file button is dead. A person has to look. Nothing goes to the government automatically.",
  },
  {
    n: 5,
    id: "detail",
    title: "A person signs, then we file",
    body: "The EHS lead approves with their name and a note. Only then is a mock regulator given a packet — and you get a reference number.",
  },
  {
    n: 6,
    id: "radar",
    title: "Look across all 12 sites",
    body: "The same unguarded conveyor can be a crush injury at one plant and a near-miss at five others. That is the point of the product.",
  },
];

function hoursLabel(h) {
  if (h == null || Number.isNaN(h)) return "—";
  const abs = Math.abs(h);
  const sign = h < 0 ? "late" : "left";
  const hr = Math.floor(abs);
  const min = Math.floor((abs - hr) * 60);
  if (h < 0) return `${hr}h ${String(min).padStart(2, "0")}m late`;
  return `${hr}h ${String(min).padStart(2, "0")}m ${sign}`;
}

function stateWords(state) {
  if (state === "missed") return { label: "Deadline missed", hint: "Filing late is itself a violation" };
  if (state === "critical") return { label: "Act now", hint: "Less than 4 hours left" };
  if (state === "warning") return { label: "Today", hint: "Less than 12 hours left" };
  return { label: "On track", hint: "More than 12 hours left" };
}

function useClock(dueAt) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const remaining = (new Date(dueAt).getTime() - now) / 3600000;
  let state = "ok";
  if (remaining < 0) state = "missed";
  else if (remaining < 4) state = "critical";
  else if (remaining < 12) state = "warning";
  return { remaining, state };
}

function FlowStrip({ active, onJump }) {
  return (
    <ol className="flow">
      {STEPS.map((s) => (
        <li key={s.n} className={active === s.id ? "active" : ""}>
          <button type="button" onClick={() => onJump(s.id)}>
            <span className="n">{s.n}</span>
            <span className="t">{s.title}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

function Story({ summary, onJump, onIntake }) {
  return (
    <div className="story">
      <header className="hero-block">
        <p className="eyebrow">RocketRide Buildathon · Problem 20</p>
        <h1>A workplace injury comes in as a messy message. SafeSync turns it into a legal deadline, two independent AI checks, and a human sign-off.</h1>
        <p className="lede big">
          Nothing is filed with a regulator until a person named Priyanka (or whoever you type) says yes. The
          government endpoint in this demo is fake. Everything before that — the law, the clocks, the disagreement
          block — is real.
        </p>
        <div className="hero-actions">
          <button className="primary lg" onClick={onIntake}>
            Start with a field report
          </button>
          <button className="lg" onClick={() => onJump("clock")}>
            Skip to live deadlines
          </button>
        </div>
      </header>

      <div className="stat-row">
        <div>
          <b>{summary?.open_clocks ?? "—"}</b>
          <span>deadlines still open</span>
        </div>
        <div>
          <b>{summary?.missed ?? "—"}</b>
          <span>already late</span>
        </div>
        <div>
          <b>{summary?.blocked ?? "—"}</b>
          <span>held because AIs disagree</span>
        </div>
        <div>
          <b>{summary?.sites ?? 12}</b>
          <span>sites on one board</span>
        </div>
      </div>

      <h2 className="plain">How a non-technical person should read this</h2>
      <div className="step-grid">
        {STEPS.map((s) => (
          <article key={s.n} className="step-card">
            <div className="n">{s.n}</div>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
            <button className="link" onClick={() => onJump(s.id)}>
              Show me this on the live board →
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}

function CardClock({ card, onOpen }) {
  const { remaining, state } = useClock(card.due_at);
  const words = stateWords(state);
  return (
    <button className={`clock-card ${state}`} onClick={() => onOpen(card.incident_id)}>
      <div className="clock-top">
        <span className="pill">{card.site_name}</span>
        <span className={`state-chip ${state}`}>{words.label}</span>
      </div>
      <div className="countdown">{hoursLabel(remaining)}</div>
      <p className="hint">{words.hint}</p>
      <div className="authority">Tell: {card.authority}</div>
      <div className="form-line">Form: {card.form}</div>
      <p className="one-liner">{card.one_liner}</p>
      <div className="id-row">Case {card.incident_id}</div>
    </button>
  );
}

function ClockBoard({ data, onOpen, onIntake }) {
  const grouped = useMemo(() => {
    const g = {};
    for (const c of data?.cards || []) (g[c.site_name] ||= []).push(c);
    return g;
  }, [data]);
  const counts = useMemo(() => {
    const c = { missed: 0, critical: 0, warning: 0, ok: 0 };
    const now = Date.now();
    for (const card of data?.cards || []) {
      const remaining = (new Date(card.due_at).getTime() - now) / 3600000;
      if (remaining < 0) c.missed += 1;
      else if (remaining < 4) c.critical += 1;
      else if (remaining < 12) c.warning += 1;
      else c.ok += 1;
    }
    return c;
  }, [data]);

  return (
    <div>
      <div className="hero">
        <div>
          <h1>Deadlines that are already running</h1>
          <p className="lede">
            Each card is one legal notice you still owe. Colour is time left — not how bad the injury was. Click a card
            to read the actual law.
          </p>
        </div>
        <button className="primary lg" onClick={onIntake}>
          New field report
        </button>
      </div>
      <div className="legend">
        <span className="swatch missed" /> Missed ({counts.missed})
        <span className="swatch critical" /> Under 4 hours ({counts.critical})
        <span className="swatch warning" /> Under 12 hours ({counts.warning})
        <span className="swatch ok" /> Later ({counts.ok})
      </div>
      <div className="capa-strip">
        Corrective actions still open: <b>{data?.capa?.open ?? 0}</b>
        {" · "}
        Overdue: <b className="warn">{data?.capa?.overdue ?? 0}</b>
        <span className="muted"> — fixing the hazard, not just filing the form.</span>
      </div>
      {Object.keys(grouped).length === 0 && <p className="lede">No open clocks. Seed the database and refresh.</p>}
      {Object.entries(grouped).map(([site, cards]) => (
        <section key={site} className="site-block">
          <h2 className="plain">{site}</h2>
          <div className="card-grid">
            {cards.map((c) => (
              <CardClock key={c.obligation_id} card={c} onOpen={onOpen} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function yesNo(v) {
  if (v === true) return "Yes — must report";
  if (v === false) return "No — not a legal report";
  return "—";
}

function AgentPane({ title, payload, highlight, subtitle }) {
  if (!payload) return <div className="pane muted">This AI has not answered yet.</div>;
  return (
    <div className="pane">
      <h3>{title}</h3>
      <p className="muted">{subtitle}</p>
      <p className={`verdict ${payload.reportable ? "yes" : "no"}`}>{yesNo(payload.reportable)}</p>
      <p className="muted">How sure: {Math.round(Number(payload.confidence || 0) * 100)}%</p>
      <p className="muted">{payload.escalate ? "This AI wants a human — facts are missing." : "This AI thinks it has enough facts."}</p>
      <ul className="obl-list">
        {(payload.obligations || []).length === 0 && <li className="muted">No legal notices suggested</li>}
        {(payload.obligations || []).map((o) => (
          <li key={o.clause_id} className={highlight && highlight.has(o.clause_id) ? "diff" : ""}>
            {o.clause_id} · {o.window_hours} hours · {o.form}
          </li>
        ))}
      </ul>
      {payload.escalation_reason && <p className="note">Missing: {payload.escalation_reason}</p>}
      {payload.disagreement_notes && <p className="note">{payload.disagreement_notes}</p>}
    </div>
  );
}

function Queue({ data, onOpen, reload }) {
  const [note, setNote] = useState("");
  const [approver, setApprover] = useState("Priyanka (EHS Lead)");
  const [err, setErr] = useState("");

  async function act(id, kind) {
    setErr("");
    if (!note.trim()) {
      setErr("Write a short reason. The audit log stores your name and this note.");
      return;
    }
    try {
      await post(`/api/decisions/${id}/${kind}`, { approver, note });
      setNote("");
      reload();
    } catch (e) {
      setErr(typeof e.message === "string" ? e.message : "Could not save");
    }
  }

  function Row({ item }) {
    const a = new Set((item.analyst?.obligations || []).map((o) => o.clause_id));
    const v = new Set((item.verifier?.obligations || []).map((o) => o.clause_id));
    const diff = new Set([...a, ...v].filter((x) => a.has(x) !== v.has(x)));
    return (
      <div className="queue-row">
        <div className="queue-head">
          <button className="link" onClick={() => onOpen(item.incident_id)}>
            {item.incident_id} · {item.site_name}
          </button>
          <div className="flags">
            {(item.flags || []).map((f) => (
              <span key={f} className="flag" title={f}>
                {FLAG_LABELS[f] || f}
              </span>
            ))}
          </div>
        </div>
        <p className="one-liner full">{item.raw_text}</p>
        <div className="split">
          <AgentPane title="AI 1 — Analyst" subtitle="Reads the report and the law" payload={item.analyst} highlight={diff} />
          <AgentPane title="AI 2 — Verifier" subtitle="Different model. Does not see AI 1's confidence." payload={item.verifier} highlight={diff} />
        </div>
        {item.status === "ready_for_approval" && (
          <div className="hitl-box">
            <p className="hitl-title">Human gate — type a note above, then click</p>
            <div className="actions">
              <button className="primary lg" onClick={() => act(item.decision_id, "approve")}>
                I approve filing
              </button>
              <button className="lg" onClick={() => act(item.decision_id, "reject")}>
                Send back
              </button>
            </div>
          </div>
        )}
        {item.status === "blocked" && (
          <p className="blocked-msg">
            Filing is locked. Open the case, add facts or override as EHS — the software will not send a report while
            these flags are on.
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1>Two AIs, then a person</h1>
      <p className="lede">
        Left and right should match. Yellow rows in the lists mean they cited different laws. Blocked cases cannot be
        filed. Ready cases still need your name.
      </p>
      <div className="note-bar">
        <label>
          Your name
          <input value={approver} onChange={(e) => setApprover(e.target.value)} />
        </label>
        <label className="grow">
          Why you approve or reject
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Doctor confirmed 3 days off work" />
        </label>
      </div>
      {err && <div className="err">{err}</div>}
      <h2 className="plain">Held — AIs do not agree, or facts are missing</h2>
      {(data?.blocked || []).length === 0 && <p className="muted">None right now.</p>}
      {(data?.blocked || []).map((i) => (
        <Row key={i.decision_id} item={i} />
      ))}
      <h2 className="plain" id="ready-queue">
        Ready for the EHS lead — Approve lives here
      </h2>
      <p className="lede">
        Scroll to this section. Fill <b>Your name</b> and <b>Why you approve</b> at the top, then the red button
        appears on each ready case. Blocked cases above have no File/Approve on purpose.
      </p>
      {(data?.ready || []).length === 0 && <p className="muted">None right now. Open a clearly reportable injury from Deadlines.</p>}
      {(data?.ready || []).map((i) => (
        <Row key={i.decision_id} item={i} />
      ))}
    </div>
  );
}

function CiteCard({ o, onFile }) {
  const { remaining, state } = useClock(o.due_at);
  return (
    <article className="cite">
      <header>
        <b>{o.citation}</b>
        <span className={`state-chip ${state}`}>
          {stateWords(state).label} · {hoursLabel(remaining)}
        </span>
      </header>
      <p className="meta">
        Send to {o.authority} · {o.form} · law PDF page {o.source_page} · checked against the act: {o.verified ? "yes" : "no"}
      </p>
      <p className="statute">{o.text}</p>
      <div className="actions">
        <button className="primary lg" onClick={() => onFile(o.obligation_id)}>
          File this notice with the demo regulator
        </button>
        <span className="muted">{o.status === "filed" ? "Already sent — see Filing + audit tab" : "Not sent yet — only works after EHS approval"}</span>
      </div>
    </article>
  );
}

function Detail({ id }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [fileMsg, setFileMsg] = useState("");
  const [tab, setTab] = useState("law");
  useEffect(() => {
    if (!id) return;
    setData(null);
    get(`/api/incidents/${id}`).then(setData).catch((e) => setErr(e.message));
  }, [id]);
  if (!id) {
    return (
      <p className="lede">Open a deadline card or a queue row first. That loads the full case here.</p>
    );
  }
  if (!data) return <p>Loading this case… {err}</p>;
  const flags = data.decision?.flags || [];

  async function fileOne(oid) {
    setFileMsg("");
    try {
      const r = await post(`/api/obligations/${oid}/file`, { approver: "Priyanka (EHS Lead)", note: "file" });
      setFileMsg(`Demo regulator accepted it. Keep this number: ${r.reference_no}`);
      setData(await get(`/api/incidents/${id}`));
    } catch (e) {
      setFileMsg(e.status === 409 ? "Blocked: the case is not approved yet. That 409 is the product." : e.message);
    }
  }

  return (
    <div>
      <div className="hero">
        <div>
          <h1>Case {data.incident.incident_id}</h1>
          <p>
            {data.incident.site_name} · {data.incident.site_type === "factory" ? "Factory (Factories Act)" : "Construction site (BOCW)"} ·{" "}
            {data.incident.status}
          </p>
        </div>
        <div className="flags">
          {flags.map((f) => (
            <span key={f} className="flag">
              {FLAG_LABELS[f] || f}
            </span>
          ))}
        </div>
      </div>
      <h2 className="plain">What the supervisor actually wrote</h2>
      <blockquote>{data.incident.raw_text}</blockquote>
      <div className="subtabs">
        <button className={tab === "law" ? "on" : ""} onClick={() => setTab("law")}>
          The law (read this)
        </button>
        <button className={tab === "ai" ? "on" : ""} onClick={() => setTab("ai")}>
          What the two AIs said
        </button>
        <button className={tab === "file" ? "on" : ""} onClick={() => setTab("file")}>
          Filing + audit
        </button>
      </div>
      {tab === "law" && (
        <>
          <p className="lede">This text is copied from the regulation store. The AI is not allowed to invent a section number.</p>
          {(data.obligations || []).length === 0 && <p>No legal notices were opened for this case.</p>}
          {(data.obligations || []).map((o) => (
            <CiteCard key={o.obligation_id} o={o} onFile={fileOne} />
          ))}
          {fileMsg && <div className="banner">{fileMsg}</div>}
        </>
      )}
      {tab === "ai" && (
        <div className="split">
          <AgentPane title="AI 1 — Analyst" payload={data.assessments.find((a) => a.agent_role === "analyst")?.payload} />
          <AgentPane title="AI 2 — Verifier" payload={data.assessments.find((a) => a.agent_role === "verifier")?.payload} />
        </div>
      )}
      {tab === "file" && (
        <>
          <h2 className="plain">What we sent (demo)</h2>
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Reference</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(data.filings || []).length === 0 && (
                <tr>
                  <td colSpan={3}>Nothing filed yet.</td>
                </tr>
              )}
              {(data.filings || []).map((f) => (
                <tr key={f.filing_id}>
                  <td>{f.filed_at}</td>
                  <td>{f.reference_no}</td>
                  <td>{f.http_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 className="plain">Who did what (inspector trail)</h2>
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {(data.audit || []).map((a) => (
                <tr key={a.audit_id}>
                  <td>{a.at}</td>
                  <td>{a.actor}</td>
                  <td>{a.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function prettyTag(t) {
  return (t || "").replaceAll("_", " ");
}

function Radar({ onOpen }) {
  const [list, setList] = useState([]);
  const [tag, setTag] = useState("conveyor_nip_point");
  const [detail, setDetail] = useState(null);
  useEffect(() => {
    get("/api/hazards").then((rows) => {
      setList(rows);
      if (rows[0] && !rows.find((r) => r.hazard_tag === "conveyor_nip_point")) setTag(rows[0].hazard_tag);
    });
  }, []);
  useEffect(() => {
    if (!tag) return;
    get(`/api/hazards/${encodeURIComponent(tag)}`).then(setDetail);
  }, [tag]);
  return (
    <div>
      <h1>Same danger, other sites</h1>
      <p className="lede">
        If a helper's hand is crushed on an unguarded conveyor in Badlapur, we look for the same missing guard
        everywhere else — even when people only logged a near-miss.
      </p>
      <div className="hazard-pills">
        {list.slice(0, 12).map((h) => (
          <button key={h.hazard_tag} className={tag === h.hazard_tag ? "on" : ""} onClick={() => setTag(h.hazard_tag)}>
            {prettyTag(h.hazard_tag)} · {h.sites} sites
          </button>
        ))}
      </div>
      {detail && (
        <section className="radar-detail">
          <h2 className="plain">{prettyTag(detail.hazard_tag)}</h2>
          <p className="lede">
            Seen at {detail.sites} of 12 sites. {detail.uncontrolled} events had no control recorded. {detail.overdue_capa}{" "}
            corrective actions are overdue — that raises the risk score for every site that still has this hazard.
          </p>
          <table>
            <thead>
              <tr>
                <th>Site</th>
                <th>Last seen</th>
                <th>Times with no guard / control</th>
              </tr>
            </thead>
            <tbody>
              {(detail.site_rows || []).map((s) => (
                <tr key={s.site_id}>
                  <td>{s.site_name}</td>
                  <td>{s.last_seen}</td>
                  <td>{s.uncontrolled}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Linked cases</h3>
          <ul className="linked">
            {(detail.incidents || []).map((i) => (
              <li key={i.incident_id}>
                <button className="link" onClick={() => onOpen(i.incident_id)}>
                  {i.incident_id}
                </button>
                <span>
                  {i.site_name} · {i.near_miss ? "near-miss (nobody hurt)" : "injury / event"}
                </span>
                <span className="muted">{i.raw_text.slice(0, 110)}…</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

const PRESETS = [
  {
    label: "Serious injury (demo)",
    site_id: "S-BAD-02",
    hospitalised: true,
    days_lost_est: 30,
    near_miss: false,
    hazard_tags: ["conveyor_nip_point", "guard_missing"],
    raw_text:
      "Around 2:40pm at Badlapur Unit 2, a helper's left hand was caught in the unguarded nip point of the conveyor drive during belt cleaning. He was taken to Sai Hospital, admitted, three fingers crushed. Machine was running. Supervisor stopped the line after.",
  },
  {
    label: "Unclear — 48 hours?",
    site_id: "S-KLY-01",
    hospitalised: false,
    days_lost_est: 1,
    near_miss: false,
    hazard_tags: ["manual_handling"],
    raw_text:
      "Helper twisted ankle on packing floor. Occupational health put a crepe bandage and sent him home. He might try light duty tomorrow. Not admitted. We do not know if he will miss 48 hours.",
  },
  {
    label: "Near-miss only",
    site_id: "S-KLY-01",
    hospitalised: false,
    days_lost_est: 0,
    near_miss: true,
    hazard_tags: ["conveyor_nip_point", "guard_missing"],
    raw_text:
      "Near miss on packing conveyor. Glove almost went into the unguarded nip at the tail pulley. Machine still running. Guard missing since last week. No injury.",
  },
];

function Intake({ sites, onClose, onCreated }) {
  const [form, setForm] = useState(PRESETS[0]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const r = await post("/api/incidents", {
        site_id: form.site_id,
        raw_text: form.raw_text,
        hospitalised: form.hospitalised,
        near_miss: form.near_miss,
        hazard_tags: form.hazard_tags,
        days_lost_est: form.days_lost_est,
      });
      onCreated(r.incident_id);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Paste how it actually arrives</h2>
        <p className="lede">Pick a demo script or type. SafeSync will look up the law, run two AIs, and start clocks.</p>
        <div className="presets">
          {PRESETS.map((p) => (
            <button key={p.label} className={form.label === p.label ? "on" : ""} onClick={() => setForm({ ...p })}>
              {p.label}
            </button>
          ))}
        </div>
        <label>
          Site
          <select value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
            {sites.map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.name} — {s.type}
              </option>
            ))}
          </select>
        </label>
        <textarea rows={7} value={form.raw_text} onChange={(e) => setForm({ ...form, raw_text: e.target.value })} />
        <label className="check">
          <input
            type="checkbox"
            checked={form.hospitalised}
            onChange={(e) => setForm({ ...form, hospitalised: e.target.checked })}
          />
          Worker was admitted to hospital
        </label>
        <div className="actions">
          <button className="primary lg" disabled={busy} onClick={submit}>
            {busy ? "Both AIs are reading the law…" : "Run SafeSync"}
          </button>
          <button onClick={onClose}>Cancel</button>
        </div>
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  );
}

const NAV = [
  ["story", "How it works"],
  ["clock", "1. Deadlines"],
  ["queue", "2. Two AIs"],
  ["detail", "3. The case"],
  ["radar", "4. Other sites"],
];

export default function App() {
  const [tab, setTab] = useState("story");
  const [board, setBoard] = useState(null);
  const [queue, setQueue] = useState(null);
  const [summary, setSummary] = useState(null);
  const [incidentId, setIncidentId] = useState(null);
  const [sites, setSites] = useState([]);
  const [intake, setIntake] = useState(false);
  const [apiDown, setApiDown] = useState(false);

  function reload() {
    Promise.all([get("/api/clock-board"), get("/api/queue"), get("/api/sites"), get("/api/summary")])
      .then(([b, q, s, sum]) => {
        setBoard(b);
        setQueue(q);
        setSites(s);
        setSummary(sum);
        setApiDown(false);
      })
      .catch(() => setApiDown(true));
  }
  useEffect(() => {
    reload();
    const t = setInterval(reload, 20000);
    return () => clearInterval(t);
  }, []);

  function open(id) {
    setIncidentId(id);
    setTab("detail");
    setIntake(false);
  }

  return (
    <div className="app">
      <aside>
        <div className="brand">
          SafeSync
          <small>Safety reporting, with a human still in charge</small>
        </div>
        <nav>
          {NAV.map(([id, label]) => (
            <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
        <button className="primary" onClick={() => setIntake(true)}>
          New field report
        </button>
        <p className="aside-foot">
          Clocks tick on this screen. RocketRide Cloud runs the two AI models when you connect it. The regulator box is
          a demo.
        </p>
      </aside>
      <main>
        {apiDown && (
          <div className="err">
            Cannot reach the SafeSync server. Start it with: python -m uvicorn app.main:app --port 8000
          </div>
        )}
        {tab !== "story" && <FlowStrip active={tab} onJump={setTab} />}
        {tab === "story" && <Story summary={summary} onJump={setTab} onIntake={() => setIntake(true)} />}
        {tab === "clock" && <ClockBoard data={board} onOpen={open} onIntake={() => setIntake(true)} />}
        {tab === "queue" && <Queue data={queue} onOpen={open} reload={reload} />}
        {tab === "detail" && <Detail id={incidentId} />}
        {tab === "radar" && <Radar onOpen={open} />}
      </main>
      {intake && (
        <Intake
          sites={sites}
          onClose={() => setIntake(false)}
          onCreated={(id) => {
            setIntake(false);
            reload();
            open(id);
          }}
        />
      )}
    </div>
  );
}
