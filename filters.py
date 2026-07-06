"""Filtering logic: target-company matching, CS relevance, undergrad eligibility.

This is the module that decides what actually pings you — read carefully.
"""

import re

# ---------------------------------------------------------------------------
# Target company allow-list (from CLAUDE.md, transcribed verbatim)
# ---------------------------------------------------------------------------

TARGET_COMPANIES = [
    "Renaissance Technologies", "Radix Trading", "TGS", "Arrowstreet Capital",
    "PDT Partners", "Citadel Securities", "Point72", "Jane Street", "HRT",
    "Hudson River Trading", "Jump Trading", "Ridgewater", "Quadrature Capital",
    "Optiver", "Two Sigma", "DE Shaw", "D. E. Shaw", "Five Rings", "Voleon",
    "XTX Markets", "Susquehanna", "SIG", "IMC", "DRW", "Virtu Financial",
    "Millennium", "Tower Research Capital", "AQR", "WorldQuant", "Squarepoint",
    "Akuna Capital", "Vivcourt", "G-Research", "QRT", "Wolverine Trading",
    "Old Mission", "Belvedere Trading", "CME Group", "Anthropic", "OpenAI",
    "Nvidia", "Netflix", "Roblox", "Microsoft", "Meta", "Apple", "Google",
    "Airbnb", "Block", "Tesla", "Uber", "DoorDash", "Stripe", "PayPal",
    "Square", "Coinbase", "Bloomberg", "Notion", "Asana", "Coupang",
    "Datadog", "Snap Inc", "LinkedIn", "Spotify", "Dropbox", "Pinterest",
    "Plaid", "Figma", "Discord", "Robinhood", "Amazon", "Adobe", "Blackstone",
    "eBay", "X", "GitHub", "Oracle", "Lyft", "Twitch", "Atlassian",
    "Salesforce", "Capital One", "JPMorgan", "JPMC", "Morgan Stanley",
    "Intel", "Booking.com", "BlackRock", "IBM", "Citi", "Wells Fargo",
    "Goldman Sachs", "Booz Allen", "Walmart", "AppLovin", "TCS",
    "Tata Consultancy", "HCLTech", "Infosys", "Anduril", "SpaceX", "Palantir",
    "Scale AI", "Snowflake", "Databricks", "Cruise", "Waymo", "ByteDance",
    "TikTok", "Cisco", "VMware", "Airtable", "Rippling", "Ramp", "Brex",
    "Instacart", "Zillow", "Affirm", "Chime", "Wealthfront", "Epic Systems",
    "Palo Alto Networks", "CrowdStrike", "Okta", "HashiCorp", "MongoDB",
    "Confluent", "Elastic", "Cloudflare", "Twilio", "ServiceNow", "Workday",
    "Zoom", "Reddit", "Duolingo", "Canva", "Vercel", "Perplexity", "xAI",
    "Mistral", "Cohere", "Character.AI", "Applied Intuition", "Rivian",
    "Lucid Motors", "AMD", "ASML", "Samsung Research", "Yelp", "Etsy",
    "Shopify", "Squarespace", "Wix", "New Relic", "PagerDuty", "Splunk",
    "DeepMind", "CoreWeave", "Cerebras", "Groq", "Safe Superintelligence",
    "SSI", "Hugging Face", "Weights & Biases", "Qualcomm", "Arm", "Synopsys",
    "Cadence", "Replit",
]

# Alternate renderings of companies already on the list, so a different
# spelling in the tracker data doesn't slip past the word-boundary match.
COMPANY_ALIASES = [
    "Snap",            # "Snap Inc" is usually listed as just "Snap"
    "Citigroup",       # "Citi" won't word-boundary-match "Citigroup"
    "D.E. Shaw",       # list has "D. E. Shaw" (spaced); trackers often omit the space
    "Character AI",    # "Character.AI" sometimes rendered without the dot
]

# "X" is too fragile even with word boundaries (it matches any company with
# a standalone X in its name, e.g. "Nuclear Promise X"). Per CLAUDE.md,
# require the whole company name to BE one of these forms instead.
EXACT_ONLY = {"X": {"x", "x corp", "x corp.", "x (twitter)", "x / twitter"}}

_ALL_PATTERNS = [
    (name, re.compile(r"\b" + re.escape(name.lower()) + r"\b"))
    for name in TARGET_COMPANIES + COMPANY_ALIASES
    if name not in EXACT_ONLY
]


def is_target_company(company_name: str) -> str | None:
    """Return the matched target-list name, or None if not a target company.

    Whole-word matching against the lowercased name, so e.g. "SIG" does not
    match inside "Signify".
    """
    if not company_name:
        return None
    haystack = company_name.lower()
    for name, pattern in _ALL_PATTERNS:
        if pattern.search(haystack):
            return name
    for name, exact_forms in EXACT_ONLY.items():
        if haystack.strip() in exact_forms:
            return name
    return None


# ---------------------------------------------------------------------------
# CS relevance
# ---------------------------------------------------------------------------

# The Simplify tracker migrated its category taxonomy mid-2026; live data
# contains BOTH the old long names and the new short ones, so accept both.
CS_CATEGORIES = {
    "Software Engineering", "Software",
    "Data Science, AI & Machine Learning", "AI/ML/Data",
    "Quantitative Finance", "Quant",
    "Hardware Engineering", "Hardware",
}

# Categories where we fall back to title keywords instead of trusting the tag.
FALLBACK_CATEGORIES = {"Product Management", "Product", "Other"}

CS_TITLE_PATTERN = re.compile(
    r"\b("
    r"software|swe|engineer(?:ing)?|developer|back[- ]?end|front[- ]?end|"
    r"full[- ]?stack|machine learning|ml|ai|data scien\w*|data engineer\w*|"
    r"infrastructure|platform|systems|quant\w*|firmware|security|devops|"
    r"cloud|mobile|ios|android|embedded"
    r")\b",
    re.IGNORECASE,
)

# "research" counts only when paired with a technical qualifier.
RESEARCH_PATTERN = re.compile(r"\bresearch\b", re.IGNORECASE)
TECH_QUALIFIER_PATTERN = re.compile(
    r"\b(software|ml|ai|machine learning)\b", re.IGNORECASE
)


def _title_is_cs(title: str) -> bool:
    if CS_TITLE_PATTERN.search(title):
        return True
    return bool(RESEARCH_PATTERN.search(title) and TECH_QUALIFIER_PATTERN.search(title))


def is_cs_relevant(title: str, category: str | None = None) -> bool:
    """Simplify listings pass a category; vansh listings pass category=None."""
    if category in CS_CATEGORIES:
        return True
    # Product Management / Other / unknown category / no category at all:
    # decide from the title.
    return _title_is_cs(title or "")


# ---------------------------------------------------------------------------
# Undergrad eligibility
# ---------------------------------------------------------------------------

GRAD_DEGREES = {"Master's", "PhD", "MBA"}

GRAD_ONLY_TITLE_PATTERN = re.compile(
    r"\b(master(?:['’])?s?|mba|ph\.?\s?d|m\.?s\.?\s+in|graduate)\b",
    re.IGNORECASE,
)
UNDERGRAD_TITLE_PATTERN = re.compile(r"\bundergrad(?:uate)?\b", re.IGNORECASE)


def is_undergrad_eligible(title: str, degrees: list[str] | None = None) -> bool:
    """Simplify listings pass the degrees list; vansh listings pass None."""
    if degrees is not None:
        if not degrees:
            return True  # empty degrees list -> assume open to undergrads
        if "Bachelor's" in degrees:
            return True
        # Only Master's/PhD/MBA listed -> grad-only. Unknown values -> inclusive.
        return not set(degrees).issubset(GRAD_DEGREES)

    title = title or ""
    if UNDERGRAD_TITLE_PATTERN.search(title):
        return True
    # Note: \bgraduate\b does not match inside "undergraduate" (preceded by
    # a word character), so this only catches genuine grad-only markers.
    return not GRAD_ONLY_TITLE_PATTERN.search(title)
