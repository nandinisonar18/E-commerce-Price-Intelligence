import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
# The instance folder may not exist yet on a fresh checkout/zip extract
# (git and zip don't reliably preserve empty directories), and SQLite will
# fail with "unable to open database file" rather than creating it for you.
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# SQLite URIs need forward slashes even on Windows -- a raw WindowsPath
# (E:\Ecommerce\...) produces a malformed sqlite:/// URI and the same
# "unable to open database file" error.
_DEFAULT_DB_PATH = (INSTANCE_DIR / "price_intel.db").as_posix()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Scraping behaviour
    REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", 8))
    MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 2))
    BACKOFF_BASE_SECONDS = float(os.environ.get("BACKOFF_BASE_SECONDS", 0.6))
    MAX_CONCURRENT_SCRAPES = int(os.environ.get("MAX_CONCURRENT_SCRAPES", 3))
    USER_AGENT = os.environ.get(
        "SCRAPER_USER_AGENT",
        "PriceIntelBot/1.0 (+https://example.com/bot-info; contact=you@example.com)",
    )
    RESPECT_ROBOTS_TXT = os.environ.get("RESPECT_ROBOTS_TXT", "true").lower() == "true"

    # If a live scrape fails or returns nothing (bot walls, layout changes,
    # network issues), fall back to the last cached snapshot for that source
    # so one flaky retailer never takes down the whole comparison.
    ALLOW_FIXTURE_FALLBACK = os.environ.get("ALLOW_FIXTURE_FALLBACK", "true").lower() == "true"
    FIXTURE_DIR = BASE_DIR / "fixtures"

    # Default EMI assumptions (documented, overridable per request)
    DEFAULT_INTEREST_RATE_ANNUAL = float(os.environ.get("DEFAULT_INTEREST_RATE_ANNUAL", 13.0))
    DEFAULT_TENURE_MONTHS = int(os.environ.get("DEFAULT_TENURE_MONTHS", 12))
