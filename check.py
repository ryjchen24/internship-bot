"""One-shot internship check for GitHub Actions (no persistent process).

Fetches both sources, filters, posts new matches to Discord via the REST API
(bot token — no gateway connection needed), appends a heartbeat status
message, updates seen_urls.json, and exits. The workflow commits the updated
state file back to the repo so nothing is ever re-posted.

Usage: python check.py   (reads DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID /
                          DISCORD_MENTION / HEARTBEAT from env or .env)
"""

import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv

import sources
import state
from bot import find_matches, format_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("check")

DISCORD_API = "https://discord.com/api/v10"

# Must match the cron in .github/workflows/check.yml ("9,29,49 * * * *").
SCHEDULE_MINUTES = (9, 29, 49)


def scheduled_tick(now_ts: int) -> int:
    """The most recent cron tick at or before now — what time this run was
    *supposed* to start, so the heartbeat can show GitHub's scheduling delay."""
    from datetime import datetime, timedelta, timezone

    now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    candidates = [now.replace(minute=m, second=0, microsecond=0) for m in SCHEDULE_MINUTES]
    past = [c for c in candidates if c <= now]
    if past:
        return int(max(past).timestamp())
    prev_hour = now - timedelta(hours=1)
    return int(prev_hour.replace(minute=SCHEDULE_MINUTES[-1], second=0, microsecond=0).timestamp())


def post_message(token: str, channel_id: str, content: str) -> None:
    url = f"{DISCORD_API}/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}"}
    payload = {"content": content, "allowed_mentions": {"parse": ["users"]}}
    for attempt in (1, 2):
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 429 and attempt == 1:
            wait = float(resp.json().get("retry_after", 2)) + 0.5
            log.warning("Rate limited; retrying in %.1fs", wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return


def main() -> int:
    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    mention = os.environ.get("DISCORD_MENTION", "").strip()
    heartbeat = os.environ.get("HEARTBEAT", "true").lower() not in ("false", "0", "no")
    if not token or not channel_id:
        log.error("DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set")
        return 1

    now = int(time.time())  # process start, before fetching
    listings = sources.fetch_all()
    if not listings:
        # Both sources failed — say so in the channel and fail the run so it
        # shows red in the Actions history.
        log.error("Both sources returned nothing")
        if heartbeat:
            post_message(token, channel_id,
                         f"🔴 Internship check <t:{now}:f> — both sources failed to fetch; will retry next run.")
        return 1

    first_run = not state.state_exists()
    seen = state.load_seen()
    matches = find_matches(listings)
    new = [m for m in matches if m["normalized_url"] not in seen]

    sent = 0
    if first_run:
        seen.update(l["normalized_url"] for l in listings)
        log.info("First run: pre-seeded %d URLs as baseline, no alerts sent", len(seen))
    else:
        for listing in new:
            try:
                post_message(token, channel_id, format_message(listing, mention))
                seen.add(listing["normalized_url"])
                sent += 1
                log.info("Alerted: %s — %s", listing["company"], listing["title"])
                time.sleep(1)  # stay well under Discord rate limits
            except requests.RequestException as exc:
                log.error("Failed to send alert for %s: %s", listing["url"], exc)

    state.save_seen(seen)

    if heartbeat:
        done = int(time.time())
        event = os.environ.get("GITHUB_EVENT_NAME", "local")
        if event == "schedule":
            tick = scheduled_tick(now)
            delay = now - tick
            timing = (f"cron <t:{tick}:T> → started <t:{now}:T> "
                      f"(delay {delay // 60}m{delay % 60:02d}s) → posted <t:{done}:T>")
        else:
            timing = f"{event} run, started <t:{now}:T>, posted <t:{done}:T>"
        if first_run:
            text = (f"🟢 Internship bot baseline created — {timing} — "
                    f"{len(seen)} current listings recorded; alerts start next run.")
        else:
            text = (f"🟢 Internship check — {timing} — scanned {len(listings)} listings, "
                    f"{len(matches)} matches on watchlist, {sent} new alert(s).")
        try:
            post_message(token, channel_id, text)
        except requests.RequestException as exc:
            log.error("Failed to send heartbeat: %s", exc)

    log.info("Done: %d listings, %d matches, %d new alerts sent", len(listings), len(matches), sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
