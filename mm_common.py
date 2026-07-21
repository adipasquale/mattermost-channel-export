"""Common utilities for Mattermost scripts."""

import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: requests")


def die(msg: str) -> None:
    """Exit with error message."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_mattermost_config_from_env_vars() -> tuple[str, str]:
    """Get MM_URL and MM_TOKEN from environment, exit if missing."""
    base_url = os.environ.get("MM_URL", "").rstrip("/")
    token = os.environ.get("MM_TOKEN", "")

    if not base_url:
        die("MM_URL is not set in .env")
    if not token:
        die("MM_TOKEN is not set in .env")

    return base_url, token


def get(base_url: str, token: str, path: str, params: dict | None = None) -> Any:
    """HTTP GET request to Mattermost API with rate limit handling."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{base_url}/api/v4{path}"
    resp = requests.get(url, headers=headers, params=params or {})

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 2))
        print(f"  Rate limited, waiting {retry_after}s …")
        time.sleep(retry_after)
        return get(base_url, token, path, params)

    if not resp.ok:
        die(f"GET {url} returned {resp.status_code}: {resp.text[:200]}")

    return resp.json()
