# Discord Internship Alert Bot

Pings a Discord channel whenever one of your target companies posts a new
internship, using the community-maintained [SimplifyJobs internship
tracker](https://github.com/SimplifyJobs/Summer2026-Internships) as the data
source. Runs automatically every 30 minutes via GitHub Actions — no server
required.

## Setup

### 1. Create a Discord webhook
In your Discord server: right-click your target channel → **Edit Channel**
→ **Integrations** → **Webhooks** → **New Webhook** → **Copy Webhook URL**.
Keep this private.

### 2. Create a GitHub repo
Create a new **private** GitHub repository and push these files to it
(`check_internships.py`, `seen_ids.json`, `.github/workflows/check.yml`).

### 3. Add your webhook as a secret
In the repo: **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**.
- Name: `DISCORD_WEBHOOK_URL`
- Value: (paste the webhook URL from step 1)

### 4. Enable Actions
Go to the **Actions** tab of the repo and click **"I understand my
workflows, go ahead and enable them"** if prompted. The workflow will now
run automatically every 30 minutes.

### 5. Test it
Go to **Actions** → **Check Internships** → **Run workflow** to trigger it
manually and confirm it works. Check the logs for how many new postings it
found (should be 0 on first run since `seen_ids.json` was pre-seeded with
everything currently listed).

## Customizing

- **Company list**: edit the `COMPANIES` list at the top of
  `check_internships.py`.
- **Check frequency**: edit the `cron` line in
  `.github/workflows/check.yml` (format: minute hour day month weekday).
- **Next internship season**: SimplifyJobs creates a new repo each year
  (e.g. `Summer2027-Internships`). Update `LISTINGS_URL` in
  `check_internships.py` when that happens.

## How it works

1. GitHub Actions runs `check_internships.py` on a schedule.
2. The script downloads SimplifyJobs' `listings.json`, which is updated
   automatically multiple times a day.
3. It filters for company-name matches against your list (whole-word
   matching, so short names like "SIG" won't false-positive on unrelated
   words).
4. Any listing ID not already in `seen_ids.json` gets posted to your
   Discord webhook, then added to `seen_ids.json`.
5. The workflow commits the updated `seen_ids.json` back to the repo so
   state persists between runs.

## Limitations

- Coverage depends on SimplifyJobs' tracker. It's actively maintained and
  covers most of your list well, but a few niche quant firms (e.g. very
  small/private shops) may be under-covered — check their careers pages
  directly if a specific company matters a lot to you.
- If SimplifyJobs changes their JSON file location or schema, the script
  will need a small update.
