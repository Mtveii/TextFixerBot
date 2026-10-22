"""Container healthcheck (used by Dockerfile HEALTHCHECK).

- WEBHOOK mode: probes GET /health on the local webhook port.
- Polling mode: checks that the main process (PID 1) is alive.
Exit code 0 = healthy, 1 = unhealthy.
"""
from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    if os.environ.get("WEBHOOK_URL"):
        port = os.environ.get("WEBHOOK_PORT", "8080")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=4).read()
            return 0
        except Exception:
            return 1
    try:
        os.kill(1, 0)
        return 0
    except PermissionError:
        # process exists but belongs to another user — still alive
        return 0
    except OSError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
