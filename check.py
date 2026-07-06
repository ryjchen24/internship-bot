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

# Timing comes from the workflow's own sleep loop (see check.yml), so this is
# only used to tell the reader when to expect the next heartbeat.
INTERVAL_MINUTES = 20


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
            sep = "─" * 28
            post_message(token, channel_id, "\n".join([
                sep,
                "🔴 **Internship Check — FAILED**",
                f"▶️ Ran: <t:{now}:T>",
                "⚠️ Both sources failed to fetch; will retry next run",
                sep,
            ]))
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
        next_check = done + INTERVAL_MINUTES * 60
        sep = "─" * 28
        n_targets = sum(1 for m in matches if m.get("is_target"))
        lines = [sep, "🟢 **Internship Check**", f"▶️ Checked: <t:{now}:T>"]
        if first_run:
            lines.append(f"📊 Baseline created: {len(seen)} current listings recorded — alerts start next check")
        else:
            lines.append(
                f"📊 Scanned {len(listings)} listings • {len(matches)} CS matches "
                f"({n_targets} watchlist ⭐) • **{sent} new alert(s)**"
            )
        lines.append(f"⏭️ Next check: <t:{next_check}:t> (<t:{next_check}:R>)")
        lines.append(sep)
        text = "\n".join(lines)
        try:
            post_message(token, channel_id, text)
        except requests.RequestException as exc:
            log.error("Failed to send heartbeat: %s", exc)

    log.info("Done: %d listings, %d matches, %d new alerts sent", len(listings), len(matches), sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
