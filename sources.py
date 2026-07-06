"""Fetch + normalize all listing sources into one shape.

Sources: the two tracker JSONs (SimplifyJobs + vanshb03) plus direct
career-board APIs (Greenhouse/Lever/Ashby) for the watchlist companies in
direct_boards.json.

Common internal shape:
    {id, company, title, url, normalized_url, locations, source_repo,
     category, degrees, date_posted}
category/degrees are None for sources that don't provide them.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import requests

log = logging.getLogger(__name__)

# Populated by fetch_all() so the heartbeat can report a source breakdown.
LAST_STATS: dict = {}

SIMPLIFY_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships"
    "/dev/.github/scripts/listings.json"
)
# NOTE: this repo is renamed each year (Summer2026 -> Summer2027 -> ...).
# If this 404s, check github.com/vanshb03 for the current repo name.
VANSH_URL = (
    "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships"
    "/dev/.github/scripts/listings.json"
)

SIMPLIFY_NAME = "SimplifyJobs"
VANSH_NAME = "vanshb03"

FETCH_TIMEOUT = 30


def normalize_url(url: str) -> str:
    """Canonical form for dedup: drop query params/fragment (UTM tracking etc.),
    lowercase scheme+host, strip trailing slash."""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return url.strip().lower()
    normalized = urlunparse(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", "", "")
    )
    return normalized


def _fetch_json(url: str) -> list | None:
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.error("Fetch failed for %s: %s", url, exc)
        return None
    except ValueError as exc:
        log.error("Invalid JSON from %s: %s", url, exc)
        return None


def _normalize(raw: dict, source_repo: str) -> dict | None:
    url = raw.get("url") or ""
    if not url:
        return None
    return {
        "id": raw.get("id"),
        "company": raw.get("company_name") or "",
        "title": raw.get("title") or "",
        "url": url,
        "normalized_url": normalize_url(url),
        "locations": raw.get("locations") or [],
        "source_repo": source_repo,
        "category": raw.get("category"),   # None for vansh
        "degrees": raw.get("degrees"),     # None for vansh
        "date_posted": raw.get("date_posted") or raw.get("date_updated"),
    }


def _fetch_source(url: str, source_repo: str) -> list[dict]:
    """Fetch one source; returns [] on any failure so one bad fetch never
    takes down the whole poll."""
    data = _fetch_json(url)
    if data is None:
        return []
    listings = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        if not raw.get("active", True) or not raw.get("is_visible", True):
            continue
        normalized = _normalize(raw, source_repo)
        if normalized:
            listings.append(normalized)
    LAST_STATS[source_repo] = len(listings)
    log.info("Fetched %d active listings from %s", len(listings), source_repo)
    return listings


def fetch_simplify() -> list[dict]:
    return _fetch_source(SIMPLIFY_URL, SIMPLIFY_NAME)


def fetch_vansh() -> list[dict]:
    return _fetch_source(VANSH_URL, VANSH_NAME)


# ---------------------------------------------------------------------------
# Direct career-board APIs (Greenhouse / Lever / Ashby)
# ---------------------------------------------------------------------------

DIRECT_BOARDS_FILE = os.path.join(os.path.dirname(__file__), "direct_boards.json")

# Career boards list ALL jobs, not just internships — keep intern/co-op only.
# \bintern\b does not match "internal"/"international".
INTERN_TITLE = re.compile(r"\bintern(?:ship)?s?\b|\bco-?op\b", re.IGNORECASE)


def _parse_when(val) -> int | None:
    """ISO-8601 string or epoch-milliseconds -> unix seconds."""
    if not val:
        return None
    try:
        if isinstance(val, (int, float)):
            return int(val / 1000) if val > 1e12 else int(val)
        return int(datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                   .astimezone(timezone.utc).timestamp())
    except (ValueError, OSError):
        return None


def _direct_listing(company, title, url, locations, when, ats):
    return {
        "id": None,
        "company": company,
        "title": title or "",
        "url": url,
        "normalized_url": normalize_url(url),
        "locations": [l for l in locations if l],
        "source_repo": f"{ats} (direct)",
        "category": None,
        "degrees": None,
        "date_posted": _parse_when(when),
    }


def _fetch_board(item) -> list[dict]:
    company, cfg = item
    ats, slug = cfg["ats"], cfg["slug"]
    out = []
    try:
        if ats == "greenhouse":
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                             timeout=FETCH_TIMEOUT)
            r.raise_for_status()
            for j in r.json().get("jobs", []):
                if INTERN_TITLE.search(j.get("title", "")):
                    out.append(_direct_listing(
                        company, j["title"], j["absolute_url"],
                        [(j.get("location") or {}).get("name", "")],
                        j.get("first_published") or j.get("updated_at"), ats))
        elif ats == "lever":
            r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json",
                             timeout=FETCH_TIMEOUT)
            r.raise_for_status()
            for p in r.json():
                if INTERN_TITLE.search(p.get("text", "")):
                    out.append(_direct_listing(
                        company, p["text"], p["hostedUrl"],
                        [(p.get("categories") or {}).get("location", "")],
                        p.get("createdAt"), ats))
        elif ats == "ashby":
            r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                             timeout=FETCH_TIMEOUT)
            r.raise_for_status()
            for j in r.json().get("jobs", []):
                if INTERN_TITLE.search(j.get("title", "")):
                    locs = [j.get("location", "")] + [
                        s.get("location", "") for s in j.get("secondaryLocations") or []]
                    out.append(_direct_listing(
                        company, j["title"], j.get("jobUrl") or j.get("applyUrl"),
                        locs, j.get("publishedAt"), ats))
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("Direct board %s/%s failed: %s", ats, slug, exc)
    return [l for l in out if l["url"]]


def fetch_direct() -> list[dict]:
    """Poll every verified company career board; one bad board never breaks
    the rest. Returns intern/co-op postings only."""
    try:
        with open(DIRECT_BOARDS_FILE, encoding="utf-8") as f:
            boards = json.load(f)
    except (OSError, ValueError) as exc:
        log.error("Could not read %s: %s", DIRECT_BOARDS_FILE, exc)
        return []
    listings: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for board_listings in ex.map(_fetch_board, boards.items()):
            listings.extend(board_listings)
    LAST_STATS["direct_boards"] = len(boards)
    LAST_STATS["direct_listings"] = len(listings)
    log.info("Fetched %d intern postings from %d direct career boards",
             len(listings), len(boards))
    return listings


def fetch_all() -> list[dict]:
    """Fetch trackers + direct boards, de-duplicated by normalized URL. When
    the same job appears in several sources, keep the richer (Simplify) entry
    and record every source name in `source_repos`."""
    merged: dict[str, dict] = {}
    for listing in fetch_simplify() + fetch_vansh() + fetch_direct():
        key = listing["normalized_url"]
        if key in merged:
            existing = merged[key]
            if listing["source_repo"] not in existing["source_repos"]:
                existing["source_repos"].append(listing["source_repo"])
            # Prefer Simplify's category/degrees metadata if we saw vansh first.
            if existing["category"] is None and listing["category"] is not None:
                existing["category"] = listing["category"]
                existing["degrees"] = listing["degrees"]
        else:
            listing["source_repos"] = [listing["source_repo"]]
            merged[key] = listing
    return list(merged.values())
