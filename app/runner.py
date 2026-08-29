from __future__ import annotations

"""RocketRide client wrapper. Live demo uses Groq from Python (documented fallback)."""

import os


async def rocketride_available() -> bool:
    try:
        from rocketride import RocketRideClient
    except ImportError:
        return False
    uri = os.environ.get("ROCKETRIDE_URI")
    if not uri:
        return False
    try:
        client = RocketRideClient()
        await client.connect()
        await client.disconnect()
        return True
    except Exception:
        return False
