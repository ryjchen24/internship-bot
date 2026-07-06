# CS Internship Discord Alert Bot

Watches two community-maintained internship trackers and pings a Discord
channel whenever one of ~150 target companies posts a new **CS/software**
internship that is **undergrad-eligible**.

**Sources**
- [SimplifyJobs/Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships) (rich schema: category + degrees fields)
- [vanshb03/Summer2027-Internships](https://github.com/vanshb03/Summer2027-Internships) (leaner schema: CS relevance and degree level inferred from the title)

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

## Deployment (24/7)

**Railway.app (recommended):** push this repo to GitHub (`.env` is
gitignored), create a new Railway project from it, set `DISCORD_BOT_TOKEN`,
`DISCORD_CHANNEL_ID` (and optionally `DISCORD_MENTION`) as environment
variables. The included `Procfile` starts `python bot.py`. **Attach a Railway
volume** and set `SEEN_URLS_FILE` to a path on that volume (e.g.
`/data/seen_urls.json`) so redeploys don't wipe the alert history and re-post
everything.

**Fly.io:** `fly launch`, then
`fly secrets set DISCORD_BOT_TOKEN=... DISCORD_CHANNEL_ID=...`, mount a volume
for the state file, and `fly deploy`.

## Files

| File | Purpose |
|---|---|
| `bot.py` | Discord client, 20-min polling loop, `--dry-run` mode |
| `sources.py` | Fetch + normalize both JSON sources, cross-source dedup |
| `filters.py` | Target-company / CS-relevance / undergrad-eligibility logic |
| `state.py` | Load/save `seen_urls.json` (already-alerted URLs) |
