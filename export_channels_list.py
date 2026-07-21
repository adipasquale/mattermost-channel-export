#!/usr/bin/env python3
"""
Export Mattermost channels you have access to as TSV.

Edit the TSV file to select which channels to export, then use export.py.

Usage:
    uv run --env-file .env select_channels.py [-o output.tsv]

Arguments:
    -o, --output     Output TSV file (default: channels.tsv)

Environment (.env):
    MM_URL           Base URL of your Mattermost instance
    MM_TOKEN         Personal access token
"""

import os
import sys
import argparse
from datetime import datetime, timezone

from mm_common import get_mattermost_config_from_env_vars, die, get


parser = argparse.ArgumentParser(description="Export accessible channels to TSV")
parser.add_argument(
    "-o",
    "--output",
    default="channels.tsv",
    help="Output TSV file (default: channels.tsv)",
)
args = parser.parse_args()

BASE_URL, TOKEN = get_mattermost_config_from_env_vars()
OUTPUT_FILE = args.output


def fetch_user_channels() -> list[dict]:
    """Fetch only open/private channels the user is a member of."""
    all_channels: list[dict] = []
    print("Fetching channels…")

    # Get user's channels (only ones they're a member of)
    channels = get(BASE_URL, TOKEN, "/users/me/channels")
    if not isinstance(channels, list):
        channels = []

    for channel in channels:
        # Only include open (O) and private (P) channels, skip direct (D) messages
        channel_type = channel.get("type", "")
        if channel_type not in ("O", "P"):
            continue

        all_channels.append({
            "id": channel.get("id"),
            "name": channel.get("name"),
            "type": channel.get("type"),
            "messages_count": channel.get("total_msg_count", 0),
        })

    print(f"Found {len(all_channels)} channels")
    return sorted(all_channels, key=lambda c: c["name"])


def export_tsv(channels: list[dict], output_file: str) -> None:
    """Export channels to TSV with a select column."""
    with open(output_file, "w", encoding="utf-8") as f:
        # Header
        f.write("name\tid\ttype\tmember_count\n")

        # Rows (all marked 'yes' by default)
        for ch in channels:
            channel_type = "Open" if ch["type"] == "O" else "Private"
            f.write(
                f"{ch['name']}\t{ch['id']}\t{channel_type}\t{ch['member_count']}\n"
            )

    print(f"Exported to {output_file}")
    print(f"Remove channels you do not want to export from {output_file}")
    print("Then run: uv run --env-file .env export.py")


if __name__ == "__main__":
    channels = fetch_user_channels()
    export_tsv(channels, OUTPUT_FILE)
