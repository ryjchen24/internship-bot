"""CS Internship Discord Alert Bot.

Watches the SimplifyJobs and vanshb03 internship trackers and pings a
Discord channel when one of the target companies posts a new
CS-relevant, undergrad-eligible internship.

Usage:
    python bot.py            # run the real bot (needs .env)
    python bot.py --dry-run  # fetch + filter + print matches, no Discord
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

import sources
import state
from filters import is_cs_relevant, is_target_company, is_undergrad_eligible

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bot")

POLL_MINUTES = 20


def find_matches(listings: list[dict]) -> list[dict]:
    """Run the full filter pipeline over merged listings."""
    matches = []
    for listing in listings:
        if not is_target_company(listing["company"]):
            continue
        if not is_cs_relevant(listing["title"], listing["category"]):
            continue
        if not is_undergrad_eligible(listing["title"], listing["degrees"]):
            continue
        matches.append(listing)
    return matches


def format_message(listing: dict, mention: str = "") -> str:
    locs = listing["locations"]
    if len(locs) > 6:
        locations = ", ".join(locs[:6]) + f" (+{len(locs) - 6} more)"
    else:
        locations = ", ".join(locs) or "Location not listed"
    srcs = ", ".join(listing["source_repos"])
    lines = [
        f"🚨 **{listing['company']}** — {listing['title']}",
        f"📍 {locations}",
        f"🔗 {listing['url']}",
        f"📦 Source: {srcs}",
    ]
    body = "\n".join(lines)
    if mention:
        body = f"{mention}\n{body}"
    # Discord hard-rejects messages over 2000 chars; an oversized alert would
    # 400 on every run and never get marked seen.
    if len(body) > 1990:
        body = body[:1990] + "…"
    return body


def run_poll(seen: set[str]) -> list[dict]:
    """One poll cycle: fetch, filter, return matches not yet alerted on.
    Does NOT mutate seen — caller marks URLs seen after a successful send."""
    listings = sources.fetch_all()
    matches = find_matches(listings)
    new = [m for m in matches if m["normalized_url"] not in seen]
    log.info(
        "Poll complete: %d listings fetched, %d target-company matches, %d new",
        len(listings), len(matches), len(new),
    )
    return new


def dry_run() -> None:
    """Fetch both sources, run the filter pipeline, print matches. Never
    touches Discord or seen_urls.json."""
    listings = sources.fetch_all()
    matches = find_matches(listings)
    print(f"\nFetched {len(listings)} deduplicated active listings.")
    print(f"{len(matches)} pass all filters (target company + CS + undergrad):\n")
    for m in sorted(matches, key=lambda x: x["company"].lower()):
        print(format_message(m))
        print("-" * 60)
    print(f"\nTotal matches: {len(matches)}")


def run_bot() -> None:
    import discord
    from discord.ext import tasks

    load_dotenv()
    token = os.environ.get("DISCORD_BOT_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    mention = os.environ.get("DISCORD_MENTION", "").strip()
    if not token or not channel_id:
        log.error("DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID must be set (see .env.example)")
        sys.exit(1)
    channel_id = int(channel_id)

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    seen = state.load_seen()

    @tasks.loop(minutes=POLL_MINUTES)
    async def poll():
        try:
            # First run with no state file: pre-seed with everything currently
            # live so we don't dump hundreds of messages, then alert only on
            # listings that appear after this baseline.
            if not state.state_exists():
                listings = sources.fetch_all()
                if not listings:
                    log.warning("Baseline fetch got nothing; will retry next poll")
                    return
                seen.update(l["normalized_url"] for l in listings)
                state.save_seen(seen)
                log.info("First run: pre-seeded %d URLs as baseline, no alerts sent", len(seen))
                return

            new = run_poll(seen)
            if not new:
                return

            channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
            for listing in new:
                try:
                    await channel.send(format_message(listing, mention))
                    seen.add(listing["normalized_url"])
                    log.info("Alerted: %s — %s", listing["company"], listing["title"])
                except discord.DiscordException as exc:
                    log.error("Failed to send alert for %s: %s", listing["url"], exc)
            state.save_seen(seen)
        except Exception:
            # Never let one bad poll kill the loop.
            log.exception("Poll cycle failed; will retry next interval")

    @client.event
    async def on_ready():
        log.info("Logged in as %s; polling every %d minutes", client.user, POLL_MINUTES)
        if not poll.is_running():
            poll.start()

    client.run(token)


def main() -> None:
    parser = argparse.ArgumentParser(description="CS internship Discord alert bot")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="fetch + filter + print matches to console instead of posting",
    )
    args = parser.parse_args()
    if args.dry_run:
        dry_run()
    else:
        run_bot()


if __name__ == "__main__":
    main()
