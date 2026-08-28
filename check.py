"""Verify RocketRide SDK and .env are configured for this workspace."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
VSCODE_SETTINGS_PATH = ROOT / ".vscode" / "settings.json"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def is_local_extension_mode() -> bool:
    """Return whether this workspace delegates connection to RocketRide's local engine."""
    if not VSCODE_SETTINGS_PATH.exists():
        return False
    try:
        settings = json.loads(VSCODE_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return settings.get("rocketride.development.connectionMode") == "local"


def local_engine_is_running() -> bool:
    """Check for the extension-managed engine without relying on its dynamic port."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq engine.exe", "/NH"],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return False
    return "engine.exe" in result.stdout.lower()


async def main() -> int:
    print("RocketRide setup check")
    print(f"Workspace: {ROOT}")

    env = load_env(ENV_PATH)
    uri = env.get("ROCKETRIDE_URI") or os.environ.get("ROCKETRIDE_URI", "")
    apikey = env.get("ROCKETRIDE_APIKEY") or os.environ.get("ROCKETRIDE_APIKEY", "")
    local_mode = is_local_extension_mode()

    if not ENV_PATH.exists():
        print("FAIL: .env is missing. Open the RocketRide sidebar, connect an engine,")
        print("      then copy .env.example to .env if the extension did not create one.")
        return 1

    ok = True
    if local_mode:
        print("OK: RocketRide extension is configured for local engine mode")
        if local_engine_is_running():
            print("OK: extension-managed local RocketRide engine is running")
        else:
            print("FAIL: local RocketRide engine is not running")
            print("      Open this workspace in VS Code to start the RocketRide extension.")
            ok = False
    if not uri:
        print("FAIL: ROCKETRIDE_URI is empty in .env")
        ok = False
    else:
        print(f"OK: ROCKETRIDE_URI={uri}")

    if not apikey and not local_mode:
        print("FAIL: ROCKETRIDE_APIKEY is empty in .env")
        print("      Set it from RocketRide: Update API Key (Command Palette).")
        ok = False
    elif not apikey:
        print("OK: no workspace API key is needed in local extension mode")
    else:
        print("OK: ROCKETRIDE_APIKEY is set")

    try:
        from rocketride import RocketRideClient
    except ImportError:
        print("FAIL: rocketride package is not installed. Activate .venv and run:")
        print("      pip install -r requirements.txt")
        return 1

    print("OK: rocketride Python SDK imported")

    if not ok:
        return 1

    if local_mode:
        print("OK: local engine uses an extension-managed dynamic port and credentials")
        return 0

    client = RocketRideClient()
    try:
        await client.connect()
        print("OK: connected to RocketRide engine")
        return 0
    except Exception as exc:
        print(f"FAIL: could not connect ({exc})")
        print("      Open the RocketRide icon in the Activity Bar and start a local engine.")
        return 1
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
