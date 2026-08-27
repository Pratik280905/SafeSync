# SafeSync
AI-powered safety incident intelligence &amp; compliance


# 🛡️ SafetySync

**AI-Powered Safety Incident Intelligence & Compliance Verification**

> Sync the incidents. Verify the decision. Keep humans in control.

SafetySync is a multi-agent AI system that helps EHS (Environment, Health & Safety) teams analyze workplace safety incidents, surface recurring hazards across sites, verify compliance recommendations through independent AI review, and route consequential decisions through human approval before anything is filed.

Instead of treating every incident report as an isolated event, SafetySync builds a shared memory of historical incidents and uses it to uncover patterns that would otherwise stay hidden across different locations.

---

## 🚨 The Problem

Organizations that operate multiple sites often handle safety incidents as one-off records.

A report like:

> "Worker slipped near an oil spill beside machine M-42 at Site 7. Minor leg injury."

can look like an isolated event — but what if similar incidents occurred at four other sites in the past year?

Traditional incident workflows are usually built to **record** what happened, not to **connect** it to everything else that has happened across the organization. On top of that, determining whether an incident needs regulatory reporting typically involves:

- Reviewing incident details
- Identifying severity
- Checking applicable requirements
- Evaluating supporting evidence
- Getting EHS sign-off
- Submitting the report
- Tracking the outcome

That's a workflow that is manual, slow, repetitive, and hard to scale.

---

## 💡 The SafetySync Approach

SafetySync combines:

- 🧠 **LLM-based incident analysis** — turns messy free-text reports into structured data
- 🔎 **Semantic search** across historical incidents
- 🤖 **Two-agent verification** — an analyst and an independent verifier
- 👤 **Human-in-the-loop approval** — nothing gets filed without a person signing off
- 📋 **Structured regulatory reporting**
- 📊 **Cross-site hazard intelligence**

The goal isn't to replace EHS professionals — it's to give them an AI co-pilot that surfaces the important connections and produces an auditable recommendation, while the final call always stays with a human.

---

## 🧠 How It Works

![SafetySync architecture: Incident Input flows into Data Extraction, which splits into Incident Memory (vector search) and a Regulatory Knowledge Base. Incident Memory feeds Cross-Site Pattern Detection. Both branches converge into Agent 1 (Compliance Analyst), then Agent 2 (Compliance Verifier), then a Human Gate. Approved incidents go to a Mock Filing API and Incident Database; rejected incidents are blocked.](./assets/architecture-diagram.svg)

---

## 🤖 Multi-Agent Architecture

SafetySync uses **two specialized agents** instead of asking a single LLM call to make the entire decision alone.

### Agent 1 — Compliance Analyst

Responsibilities:
- Analyze the structured incident
- Review the supplied regulatory requirements
- Determine whether the incident appears reportable
- Identify the applicable rule
- Provide a confidence score and supporting reasoning

```json
{
  "decision": "REPORTABLE",
  "severity": "MODERATE",
  "confidence": 0.87,
  "rule_id": "RULE-003",
  "reason": "The incident contains evidence matching the supplied reporting requirement."
}
```

### Agent 2 — Compliance Verifier

Agent 2 acts as an **independent reviewer**, not a rubber stamp. It checks Agent 1's output for:

- Unsupported assumptions
- Incorrect rule selection
- Missing evidence
- Incorrect severity
- Disagreement with the supplied regulation

```json
{
  "decision": "REPORTABLE",
  "agreement": true,
  "confidence": 0.91,
  "issues": [],
  "final_recommendation": "Proceed to human approval."
}
```

If the two agents disagree:

```
Agent 1 → REPORTABLE
Agent 2 → NOT REPORTABLE

        ↓

⚠ HUMAN REVIEW REQUIRED — filing automatically blocked
```

The system never files a report on its own. Disagreement is treated as a signal, not a bug.

---

## 🔎 Cross-Site Hazard Intelligence

This is one of SafetySync's core differentiators. Historical incidents are stored as embeddings and searched semantically, so the system can connect incidents that read very differently in plain text but describe the same underlying hazard.

**New incident:**
> "Worker slipped near an oil spill beside machine M-42 at Site 7."

**SafetySync finds:**

| Similarity | Site |
|---|---|
| 91% | SITE-02 |
| 87% | SITE-04 |
| 84% | SITE-09 |

```
⚠️ RECURRING HAZARD DETECTED
Oil spill / slippery surface — 4 sites affected
```

This lets an organization spot systemic problems instead of treating every incident as independent.

---

## 👤 Human-in-the-Loop

SafetySync follows one non-negotiable principle:

> **AI recommends. Humans decide.**

```
AI Analysis  →  Agent Verification  →  Human Approval  →  Filing
```

No incident is filed with a regulator without an explicit human approval step (e.g. via Slack).

---

## ⚙️ Core Features

| Feature | Description |
|---|---|
| 📥 Incident Intake | Receive structured or free-text incident data |
| 🧠 AI Extraction | Convert incident descriptions into structured fields |
| 🔎 Semantic Search | Find similar historical incidents |
| 🌐 Cross-Site Correlation | Detect recurring hazards across locations |
| 🤖 Multi-Agent Review | Independent analysis + verification |
| 👤 Human Approval | EHS sign-off before filing |
| 📋 Mock Regulatory Filing | Demonstrates a downstream submission flow |
| 💾 Persistence | Store incident and filing state |
| ⚠️ Disagreement Detection | Escalate conflicting agent decisions |
| 📊 Incident Dashboard | Visualize safety intelligence at a glance |

---

## 🛠️ Technology Stack

```
┌─────────────────────────────────┐
│           SafetySync            │
├─────────────────────────────────┤
│ Orchestration   → RocketRide    │
│ LLM Inference   → Groq          │
│ Vector Memory   → Vector Store  │
│ Embeddings      → Embedding API │
│ Human Approval  → Slack         │
│ Database        → SQLite        │
│ Filing          → Mock REST API │
└─────────────────────────────────┘
```

The stack is intentionally lightweight — the full demo can run without a GPU or a locally hosted LLM.

---

## 📁 Project Structure

```
SafetySync/
│
├── pipelines/
│   └── safetysync.pipe
│
├── data/
│   ├── incidents.json
│   ├── regulations.json
│   └── demo_incidents.json
│
├── api/
│   └── mock_filing_api.py
│
├── database/
│   └── safetysync.db
│
├── dashboard/
│   └── ...
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone the repository
```bash
git clone <YOUR_REPOSITORY_URL>
cd SafetySync
```

### 2. Create a virtual environment

**Windows**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file based on `.env.example`:

```
GROQ_API_KEY=your_groq_api_key
SLACK_BOT_TOKEN=your_slack_token
SLACK_CHANNEL_ID=your_channel_id
```

> ⚠️ Never commit your `.env` file to GitHub. Use `.env.example` as the shareable template.

---

## ▶️ Running the Demo

**1. Start the mock filing API**
```bash
python api/mock_filing_api.py
```

**2. Run the SafetySync pipeline** (via RocketRide) and submit an incident:

```json
{
  "incident_id": "INC-001",
  "site_id": "SITE-07",
  "description": "Worker slipped near an oil spill beside machine M-42 and suffered a minor leg injury.",
  "date": "2026-08-26"
}
```

**3. SafetySync processes it through:**

```
Input → Extraction → Historical Similarity Search → Cross-Site Pattern Detection
      → Compliance Agent → Verification Agent → Human Approval → Mock Filing → Database
```

---

## 🧪 Demo Scenarios

**Scenario 1 — Reportable Incident**
> Worker suffered a serious workplace injury.

```
Agent 1 → REPORTABLE
Agent 2 → REPORTABLE
Human   → APPROVE
Filing  → SUCCESS
```

**Scenario 2 — Non-Reportable Incident**
> Minor near-miss with no injury.

```
Agent 1 → NOT REPORTABLE
Agent 2 → NOT REPORTABLE
Human   → REVIEW
```

**Scenario 3 — Recurring Hazard**
> Oil spill causing worker slip, matched against SITE-02, SITE-04, SITE-09.

```
⚠ RECURRING HAZARD DETECTED
```

**Scenario 4 — Agent Disagreement**
```
Agent 1 → REPORTABLE
Agent 2 → NOT REPORTABLE

⚠ COMPLIANCE REVIEW REQUIRED
Automatic filing blocked. Human decision required.
```

---

## 🔐 Design Principles

1. **Human Oversight** — AI recommendations never automatically become regulatory submissions.
2. **Evidence-Based Decisions** — Agents work only from structured incident data and supplied regulatory material; they don't invent rules.
3. **Disagreement Is a Feature** — Conflicting agent outputs are surfaced for human review, not hidden.
4. **No Fabricated Regulations** — The bundled regulatory dataset is illustrative/demo content unless replaced with verified, jurisdiction-specific rules.
5. **Minimal Automation** — Automation removes repetitive work; consequential decisions stay reviewable.

---

## 📈 Roadmap

**Phase 2**
- PDF incident reports & OCR
- Audio transcription intake
- Automatic corrective-action generation
- Deadline monitoring
- Richer EHS dashboard

**Phase 3**
- Verified regulatory knowledge base
- Jurisdiction-aware compliance retrieval
- Real regulatory system integrations
- Advanced anomaly detection
- Organization-wide safety analytics

**Phase 4**
- Predictive hazard identification
- Automated safety recommendations
- Enterprise identity & access control
- Full audit trails and compliance reporting

---

## 🏆 Why SafetySync?

Most incident systems answer: *"What happened?"*

SafetySync asks: *"What happened, has this happened before, does it appear reportable, do two independent AI reviewers agree, and what should happen next?"*

That shift turns incident **reporting** into incident **intelligence**.

---

## ⚠️ Disclaimer

SafetySync is a prototype demonstrating AI-assisted safety incident analysis and workflow orchestration. The regulatory rules and filing endpoint used in this demo are illustrative/mock components and **should not be treated as legal or regulatory advice**.

A production deployment would require validation against applicable jurisdiction-specific regulations, security requirements, organizational policy, and qualified EHS/legal review.

---

## 📄 License

This project is provided for demonstration and educational purposes.
