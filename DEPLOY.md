# Stage SafeSync (RocketRide Cloud + the demo UI)

RocketRide Cloud hosts **pipelines** (the two AI nodes). The Clock Board UI is a small FastAPI app. You show both.

## A. RocketRide Cloud (the two AIs)

This is what the buildathon means by "stage on RocketRide."

1. Open [https://cloud.rocketride.ai](https://cloud.rocketride.ai) and sign in (use the buildathon code on venue day if asked).
2. Copy the **API token** from Cloud Settings. The extension often does **not** fill `.env` for you.
3. Set Cloud in `.env` (never `https://localhost:5565`):
   ```
   ROCKETRIDE_URI=https://api.rocketride.ai
   ROCKETRIDE_APIKEY=<paste token>
   ROCKETRIDE_AUTH=<same token>
   ```
   Local engine stays `ROCKETRIDE_URI=ws://localhost:5565` (no API key).
4. RocketRide sidebar → Connection Manager → Cloud, then Play on `pipelines/safetysync.pipe`.
4. Put your Groq key in `.env` as **both**:
   ```
   ROCKETRIDE_GROQ_KEY=gsk_...
   GROQ_API_KEY=gsk_...
   ```
   Cloud substitutes `${ROCKETRIDE_GROQ_KEY}` inside `pipelines/safetysync.pipe`.
5. Open `pipelines/safetysync.pipe`. Press **Play** (or Deploy on the Cloud target).
6. Paste `pipelines/CHAT_PROMPT.txt` into the Chat node.

If Cloud login fails, keep `rocketride.development.connectionMode` as `local` and still demo the UI. The README already treats Docker/Cloud as the Phase 0 fallback, not a blocker.

## B. Public demo URL (judges in a browser)

From the repo root, after `npm run build` in `ui/`:

```bash
python scripts/seed_db.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000 — **How it works** is the first screen.

Or Docker:

```bash
docker build -t safesync .
docker run -p 8000:8000 --env-file .env safesync
```

Put the same image on Railway / Render / any VM if you need a link. RocketRide Cloud does not host this React app.

## C. What to say on stage

"The pipe on RocketRide Cloud is the two models. This board is the legal clocks, the human gate, and the audit trail. The regulator POST is a mock."
