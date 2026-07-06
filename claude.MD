# Project: CS Internship Discord Alert Bot

## Goal
A Discord bot that watches two community-maintained internship-tracking
repos and pings a Discord channel whenever one of ~150 target companies
posts a new internship — filtered to **CS/software-relevant roles** and
**undergraduate eligibility** only.

## Data sources (both are JSON, not HTML — no real scraping needed)

### Source 1: SimplifyJobs (rich schema, has category + degree fields)
- Raw JSON: `https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json`
- Updated automatically multiple times a day.
- Example entry:
```json
{
  "date_updated": 1762359538,
  "sponsorship": "U.S. Citizenship is Required",
  "active": true,
  "degrees": ["Bachelor's"],
  "url": "https://...",
  "company_name": "BAE Systems",
  "title": "Software Engineering Intern IV, Summer 2026",
  "locations": ["Nashua, NH"],
  "terms": ["Summer 2026"],
  "category": "Software Engineering",
  "source": "angie-hue",
  "id": "bacc96af-...",
  "date_posted": 1762359538,
  "company_url": "",
  "is_visible": true
}
```
- `category` is one of: "Software Engineering", "Data Science, AI & Machine
  Learning", "Quantitative Finance", "Hardware Engineering", "Product
  Management", "Other". Treat the first four as CS-relevant; skip "Product
  Management" and "Other" unless the title itself clearly reads as
  technical.
- `degrees` is a list that may contain "Bachelor's", "Master's", "PhD",
  "MBA". Treat a listing as **undergrad-eligible** if `degrees` is empty
  OR contains "Bachelor's". If `degrees` contains ONLY "Master's"/"PhD"/
  "MBA" (no Bachelor's), exclude it.

### Source 2: vanshb03/Summer2027-Internships (leaner schema, no category/degrees)
- Raw JSON: `https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json`
- **Important**: this repo is renamed each year (it was
  `Summer2026-Internships`, is now `Summer2027-Internships` — check
  github.com/vanshb03 for the current name if this URL 404s later).
- Example entry (note: no `category`, no `degrees`, no `terms` field —
  instead has `season`: "Summer"/"Fall"/"Winter"/"Spring"):
```json
{
  "date_updated": 1749260792,
  "url": "https://...",
  "locations": ["New York, NY", "San Francisco, CA"],
  "sponsorship": "Other",
  "active": true,
  "company_name": "Rippling",
  "title": "Frontend Software Engineer Intern",
  "season": "Winter",
  "source": "vanshb03",
  "id": "df70fa57-...",
  "date_posted": 1749260792,
  "company_url": "",
  "is_visible": true
}
```
- Since there's no `category` or `degrees` field, CS-relevance and
  undergrad eligibility must be inferred from the `title` string with
  keyword matching:
  - **CS-relevant** if title contains (case-insensitive) any of: software,
    swe, engineer, engineering, developer, backend, frontend, full stack,
    full-stack, machine learning, ml, ai, data (science|engineer),
    infrastructure, platform, systems, quant, firmware, security,
    devops, cloud, mobile, ios, android, embedded, research (only when
    paired with a technical qualifier like "software"/"ML"/"AI").
  - **Undergrad-eligible** if title does NOT contain "master's", "mba",
    "phd", "ms in", or "graduate" as a required-degree signal.
    Titles containing "undergrad" explicitly are a strong positive
    signal; absence of a graduate-only marker is enough to include it
    (be inclusive by default — most SWE intern titles don't specify
    degree level at all and are open to undergrads).

### Deduplication across sources
Both repos pull from overlapping community submissions, so the *same*
job may appear in both files. De-duplicate on the posting `url`
(normalize by stripping query params/UTM tracking before comparing) —
not on `id`, since IDs are independently generated per repo.

## Target company list
Match `company_name` case-insensitively using **whole-word / word-boundary
matching** (not raw substring) to avoid false positives — e.g. naive
substring matching makes "SIG" incorrectly match inside "Signify". Use a
regex like `\bsig\b` against the lowercased company name.

```
Renaissance Technologies, Radix Trading, TGS, Arrowstreet Capital,
PDT Partners, Citadel Securities, Point72, Jane Street, HRT,
Hudson River Trading, Jump Trading, Ridgewater, Quadrature Capital,
Optiver, Two Sigma, DE Shaw, D. E. Shaw, Five Rings, Voleon,
XTX Markets, Susquehanna, SIG, IMC, DRW, Virtu Financial, Millennium,
Tower Research Capital, AQR, WorldQuant, Squarepoint, Akuna Capital,
Vivcourt, G-Research, QRT, Wolverine Trading, Old Mission,
Belvedere Trading, CME Group, Anthropic, OpenAI, Nvidia, Netflix,
Roblox, Microsoft, Meta, Apple, Google, Airbnb, Block, Tesla, Uber,
DoorDash, Stripe, PayPal, Square, Coinbase, Bloomberg, Notion, Asana,
Coupang, Datadog, Snap Inc, LinkedIn, Spotify, Dropbox, Pinterest,
Plaid, Figma, Discord, Robinhood, Amazon, Adobe, Blackstone, eBay, X,
GitHub, Oracle, Lyft, Twitch, Atlassian, Salesforce, Capital One,
JPMorgan, JPMC, Morgan Stanley, Intel, Booking.com, BlackRock, IBM,
Citi, Wells Fargo, Goldman Sachs, Booz Allen, Walmart, AppLovin, TCS,
Tata Consultancy, HCLTech, Infosys, Anduril, SpaceX, Palantir,
Scale AI, Snowflake, Databricks, Cruise, Waymo, ByteDance, TikTok,
Cisco, VMware, Airtable, Rippling, Ramp, Brex, Instacart, Zillow,
Affirm, Chime, Wealthfront, Epic Systems, Palo Alto Networks,
CrowdStrike, Okta, HashiCorp, MongoDB, Confluent, Elastic, Cloudflare,
Twilio, ServiceNow, Workday, Zoom, Reddit, Duolingo, Canva, Vercel,
Perplexity, xAI, Mistral, Cohere, Character.AI, Applied Intuition,
Rivian, Lucid Motors, AMD, ASML, Samsung Research, Yelp, Etsy,
Shopify, Squarespace, Wix, New Relic, PagerDuty, Splunk, DeepMind,
CoreWeave, Cerebras, Groq, Safe Superintelligence, SSI, Hugging Face,
Weights & Biases, Qualcomm, Arm, Synopsys, Cadence, Replit
```
Note: "X" as a standalone company name is fragile even with word
boundaries (it'll match anything literally named "X"). Since X/Twitter
rarely posts on these trackers, deprioritize it or verify manually.

## Reference implementation to model against
`vanshb03/internships-bot` (https://github.com/vanshb03/internships-bot)
is a real, working Discord bot that already does the "clone repo → read
listings.json → diff against previous run → post to Discord" pattern for
a single source with NO filtering. Use it as an architectural reference
for the discord.py bot structure (`on_ready`, scheduled polling loop,
`format_message`, `send_message`), but **do not** use it as-is — it
lacks company filtering and CS/undergrad filtering, and only reads one
source. Fable should write a new bot inspired by this pattern that adds:
1. Both data sources (Simplify + Vansh)
2. Company allow-list filtering (word-boundary matching)
3. CS-relevance filtering (category field for Simplify, keyword
   heuristics for Vansh)
4. Undergrad-eligibility filtering (degrees field for Simplify, keyword
   heuristics for Vansh)
5. Cross-source deduplication by normalized URL
6. Persistent "already alerted" state so restarts don't re-post

## Tech stack & structure
- Python 3.11+, `discord.py`, `requests`, `python-dotenv`
- Files to create:
  - `bot.py` — main bot: on_ready, scheduled loop (use `discord.ext.tasks.loop`,
    not a separate `schedule` library, since we're already in an async
    discord.py context)
  - `sources.py` — fetch + normalize functions for both JSON sources into
    one common internal shape: `{id, company, title, url, locations, source_repo}`
  - `filters.py` — `is_target_company()`, `is_cs_relevant()`, `is_undergrad_eligible()`
  - `state.py` — load/save `seen_urls.json` (persisted list of normalized
    URLs already alerted on)
  - `.env.example` — `DISCORD_BOT_TOKEN=`, `DISCORD_CHANNEL_ID=`
  - `requirements.txt`
  - `README.md` — setup + run instructions

## Behavior requirements
- Poll every 20 minutes (`tasks.loop(minutes=20)`; GitHub Actions cron at :09/:29/:49).
- On first run, pre-seed `seen_urls.json` with everything currently live
  so it doesn't dump hundreds of messages at once — only alert on things
  that appear in a run AFTER the bot has a baseline.
- Discord message format: **Company** — Title, location(s), link, and
  which source(s) it was found in.
- Handle fetch failures (network hiccup, repo renamed/404) by logging and
  continuing on the next poll — never crash the whole process on one bad
  fetch.
- Log to stdout what it found each run (new matches count, total fetched)
  so it's debuggable when self-hosted.

## Testing
Before wiring up Discord, add a `--dry-run` CLI flag (or a small test
script) that fetches both sources, runs the filter pipeline, and prints
matches to the console instead of posting — so filtering logic can be
verified without spamming the real channel.

## Deployment / hosting
This bot uses a real Discord bot token (`discord.py`), which means it
needs to run **continuously**, not just on a schedule — unlike a
webhook+cron approach. Options, in order of recommendation:

1. **Railway.app (recommended)** — push the repo, connect it as a new
   project, set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` as
   environment variables in the Railway dashboard, and it stays running
   persistently. Free tier is sufficient for a single small bot like
   this. Add a `Procfile` or just let Railway detect `python bot.py` as
   the start command.
2. **Fly.io** — similar model: `fly launch` in the project directory,
   set secrets via `fly secrets set DISCORD_BOT_TOKEN=... DISCORD_CHANNEL_ID=...`,
   deploy with `fly deploy`. Slightly more CLI-driven than Railway but
   also has a usable free allowance.

Whichever host is used, `seen_urls.json` (or wherever state is persisted)
needs to live on a persistent volume/disk on that host, or be swapped
for a tiny external store (e.g. a Railway volume, or even just committing
it back to the git repo periodically) — otherwise a redeploy wipes the
"already alerted" history and the bot re-posts everything on next boot.

## Local build workflow (VS Code + Claude Code / Fable)
1. Create a new folder locally, open it in VS Code.
2. Drop this `CLAUDE.md` into the project root.
3. Open Claude Code (Fable) in that folder and say something like:
   *"Read CLAUDE.md and build this project."* It has everything Fable
   needs — exact JSON URLs, verified schemas, the company list, filtering
   logic, and file structure — no guesswork required.
4. Review what it writes, especially `filters.py` — that's the part
   worth reading closely since it's the logic actually deciding what
   pings you.
5. Create `.env` (copy from `.env.example`) and have spaces for user to fill in the real
   `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID`. Add `.env` to
   `.gitignore` immediately, before the first commit — never let the bot
   token land in git history.
6. Test locally with `--dry-run` first (see Testing section above), then
   run for real locally to confirm it logs in and posts correctly.
7. Once confirmed working locally, push to a GitHub repo (with `.env`
   excluded) and deploy to Railway or Fly.io per the Deployment section
   above for 24/7 uptime.