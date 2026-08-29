"""Start pipelines/safetysync.pipe on the engine in ROCKETRIDE_URI (staging Cloud)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

PIPE = ROOT / "pipelines" / "safetysync.pipe"


async def main() -> int:
    from rocketride import RocketRideClient

    async with RocketRideClient() as client:
        await client.connect()
        print("connected to staging")
        res = await client.use(filepath=str(PIPE))
        token = res.get("token") or res.get("id")
        print("pipeline started")
        print("token:", token)
        print("keys:", sorted(res.keys()))
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print("deploy failed:", type(exc).__name__, exc)
        raise SystemExit(1)
