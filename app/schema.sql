CREATE TABLE sites (
  site_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('factory','construction')),
  state         TEXT, district TEXT,
  jurisdictions TEXT NOT NULL,
  headcount     INTEGER,
  occupier      TEXT
);

CREATE TABLE incidents (
  incident_id     TEXT PRIMARY KEY,
  site_id         TEXT NOT NULL REFERENCES sites(site_id),
  occurred_at     TEXT NOT NULL,
  reported_at     TEXT NOT NULL,
  reported_by     TEXT, channel TEXT,
  raw_text        TEXT NOT NULL,
  fatality        INTEGER DEFAULT 0,
  hospitalised    INTEGER DEFAULT 0,
  days_lost_est   INTEGER,
  persons_affected INTEGER DEFAULT 1,
  control_present INTEGER DEFAULT 0,
  near_miss       INTEGER DEFAULT 0,
  bucket          TEXT,
  status          TEXT DEFAULT 'new'
);

CREATE TABLE incident_hazards (
  incident_id TEXT REFERENCES incidents(incident_id),
  hazard_tag  TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  site_id     TEXT NOT NULL,
  PRIMARY KEY (incident_id, hazard_tag)
);

CREATE TABLE clauses (
  clause_id    TEXT PRIMARY KEY,
  jurisdiction TEXT NOT NULL,
  citation     TEXT NOT NULL,
  heading      TEXT,
  authority    TEXT NOT NULL,
  form         TEXT,
  window_hours INTEGER NOT NULL,
  clock_starts TEXT NOT NULL,
  source_pdf   TEXT, source_page INTEGER,
  verified     INTEGER DEFAULT 0,
  text         TEXT NOT NULL,
  trigger_json TEXT,
  site_types   TEXT
);

CREATE TABLE assessments (
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id   TEXT NOT NULL REFERENCES incidents(incident_id),
  agent_role    TEXT NOT NULL CHECK (agent_role IN ('analyst','verifier')),
  model         TEXT NOT NULL,
  reportable    INTEGER,
  confidence    REAL,
  payload       TEXT NOT NULL,
  parse_status  TEXT DEFAULT 'ok',
  latency_ms    INTEGER,
  created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE decisions (
  decision_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id   TEXT NOT NULL REFERENCES incidents(incident_id),
  reportable    INTEGER,
  flags         TEXT NOT NULL,
  status        TEXT NOT NULL,
  approved_by   TEXT, approved_at TEXT, approver_note TEXT,
  created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE obligations (
  obligation_id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id   TEXT NOT NULL REFERENCES incidents(incident_id),
  clause_id     TEXT NOT NULL REFERENCES clauses(clause_id),
  authority     TEXT NOT NULL,
  form          TEXT,
  due_at        TEXT NOT NULL,
  status        TEXT DEFAULT 'open',
  filed_at      TEXT
);

CREATE TABLE filings (
  filing_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  obligation_id INTEGER NOT NULL REFERENCES obligations(obligation_id),
  incident_id   TEXT NOT NULL,
  payload       TEXT NOT NULL,
  endpoint      TEXT NOT NULL,
  http_status   INTEGER,
  reference_no  TEXT,
  filed_by      TEXT NOT NULL,
  filed_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE capa (
  capa_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id  TEXT NOT NULL REFERENCES incidents(incident_id),
  site_id      TEXT NOT NULL,
  hazard_tag   TEXT,
  action       TEXT NOT NULL,
  owner        TEXT NOT NULL,
  due_at       TEXT NOT NULL,
  status       TEXT DEFAULT 'open',
  closed_at    TEXT, evidence TEXT
);

CREATE TABLE audit_log (
  audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT DEFAULT (datetime('now')),
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  entity      TEXT NOT NULL, entity_id TEXT,
  detail     TEXT
);
