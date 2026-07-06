"""Fetch + normalize both internship-tracker JSON sources into one shape.

Common internal shape:
    {id, company, title, url, normalized_url, locations, source_repo,
     category, degrees}
category/degrees are None for sources that don't provide them.
"""

import logging
from urllib.parse import urlparse, urlunparse

import requests

log = logging.getLogger(__name__)

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
    log.info("Fetched %d active listings from %s", len(listings), source_repo)
    return listings


def fetch_simplify() -> list[dict]:
    return _fetch_source(SIMPLIFY_URL, SIMPLIFY_NAME)


def fetch_vansh() -> list[dict]:
    return _fetch_source(VANSH_URL, VANSH_NAME)


def fetch_all() -> list[dict]:
    """Fetch both sources and de-duplicate by normalized URL. When the same
    job appears in both repos, keep the richer (Simplify) entry and record
    both source names in `source_repos`."""
    merged: dict[str, dict] = {}
    for listing in fetch_simplify() + fetch_vansh():
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
