"""Persistent 'already alerted' state: a JSON list of normalized URLs."""

import json
import logging
import os

log = logging.getLogger(__name__)

STATE_FILE = os.environ.get("SEEN_URLS_FILE", "seen_urls.json")


def state_exists() -> bool:
    return os.path.exists(STATE_FILE)


def load_seen() -> set[str]:
    if not state_exists():
        return set()
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError) as exc:
        log.error("Could not read %s (%s); starting with empty state", STATE_FILE, exc)
        return set()


def save_seen(seen: set[str]) -> None:
    tmp_path = STATE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f, indent=0)
        os.replace(tmp_path, STATE_FILE)
    except OSError as exc:
        log.error("Could not write %s: %s", STATE_FILE, exc)
