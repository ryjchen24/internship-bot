# CS Internship Discord Alert Bot

Watches two community-maintained internship trackers and posts to a Discord
channel whenever a new **CS/software**, **undergrad-eligible** internship
appears — any company. Listings from the ~150 watchlist companies in
`filters.py` are starred (⭐) and ping you with an @mention; everything else
posts without a ping.

**Sources**
- [SimplifyJobs/Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships) (rich schema: category + degrees fields)
- [vanshb03/Summer2027-Internships](https://github.com/vanshb03/Summer2027-Internships) (leaner schema: CS relevance and degree level inferred from the title)
- **Direct career boards** — `direct_boards.json` maps ~76 watchlist companies
  to their public Greenhouse/Lever/Ashby APIs, polled every check, so postings
  are caught straight from the company site without waiting for the community
  trackers. Companies on custom/Workday career sites remain tracker-covered.

Listings appearing in both trackers are de-duplicated by normalized URL
(query params/UTM stripped), and the alert shows which source(s) it came from.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your token + channel ID
```

### Getting the Discord credentials

1. Go to https://discord.com/developers/applications → **New Application**.
2. Under **Bot**, click **Reset Token** and copy it into `DISCORD_BOT_TOKEN` in `.env`.
3. Under **OAuth2 → URL Generator**, check the `bot` scope and the
   **Send Messages** + **View Channels** permissions, open the generated URL,
   and invite the bot to your server.
4. In Discord, enable Developer Mode (Settings → Advanced), right-click the
   channel you want alerts in → **Copy Channel ID** → paste into
   `DISCORD_CHANNEL_ID` in `.env`.
5. Optional: set `DISCORD_MENTION=<@your_user_id>` to get pinged on every alert
   (right-click your own name → Copy User ID).

## Testing without Discord

```bash
python bot.py --dry-run
```

Fetches both sources, runs the full filter pipeline, and prints every current
match to the console — no token needed, no messages posted, no state written.

## Running

```bash
python bot.py
```

- Polls both sources every **20 minutes**.
- **First run** pre-seeds `seen_urls.json` with everything currently live and
  sends nothing — it only alerts on listings that appear *after* that baseline.
- Fetch failures (network hiccup, repo renamed) are logged and retried on the
  next poll; the process never crashes on one bad fetch.

> The vanshb03 repo is renamed every year (Summer2026 → Summer2027 → …). If its
> fetch starts 404ing, check github.com/vanshb03 for the new repo name and
> update `VANSH_URL` in `sources.py`.

## Deployment (24/7, free): GitHub Actions

This repo is set up to run **serverless** — no always-on bot process, no
hosting bill. GitHub's cron scheduler is best-effort (it routinely skips or
delays ticks), so `.github/workflows/check.yml` does NOT rely on it for
timing: each workflow run is a **~5.3-hour chain link** that runs `check.py`
every 20 minutes on an internal `sleep` timer (16 checks per link), then
dispatches the next link. The cron entry is only a watchdog that restarts
the chain if it ever dies. Each check:

1. Fetches both sources and runs the same filter pipeline as the bot.
2. Posts new matches to the channel via the Discord REST API (bot token).
3. Posts a 🟢 heartbeat block (proof of life even with no new internships)
   with a "next check" countdown — silence heartbeats by adding a repository
   **variable** `HEARTBEAT=false` under Settings → Secrets and variables →
   Actions.
4. Commits the updated `seen_urls.json` back to the repo, so state persists
   and nothing is re-posted.

Required repository **secrets** (Settings → Secrets and variables → Actions):
`DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`.

Start the chain manually from the **Actions** tab ("Internship check" → Run
workflow). Actions minutes are only unlimited/free on **public** repos.

### Alternative: always-on hosting (Railway / Fly.io)

`bot.py` still works as a persistent gateway bot if you prefer instant-ish
hosting on Railway/Fly: set `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID` (and
optionally `DISCORD_MENTION`) as env vars, use the included `Procfile`, and
put `SEEN_URLS_FILE` on a persistent volume (e.g. `/data/seen_urls.json`) so
redeploys don't wipe alert history. Don't run both deployments at once —
they'd double-post.

## Files

| File | Purpose |
|---|---|
| `check.py` | One-shot check for GitHub Actions: fetch → filter → post → save state → exit |
| `.github/workflows/check.yml` | Schedule (every 20 min), secrets wiring, state commit |
| `bot.py` | Discord client, 20-min polling loop, `--dry-run` mode |
| `sources.py` | Fetch + normalize trackers and direct career boards, cross-source dedup |
| `direct_boards.json` | Verified company → Greenhouse/Lever/Ashby board mapping |
| `filters.py` | Target-company / CS-relevance / undergrad-eligibility logic |
| `state.py` | Load/save `seen_urls.json` (already-alerted URLs) |
