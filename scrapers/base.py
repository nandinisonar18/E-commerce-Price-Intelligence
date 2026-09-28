import json
import logging
import time
import urllib.robotparser as robotparser
from datetime import datetime
from urllib.parse import urlparse

import requests

logger = logging.getLogger("price_intel.scraper")


class ScraperError(Exception):
    pass


class SourceBlockedError(ScraperError):
    """Raised when robots.txt disallows the path, or the site returns a
    bot-check response (e.g. 403/429, or a known CAPTCHA/interstitial page)."""


class BaseScraper:
    """Common plumbing every retailer adapter shares: a polite session,
    robots.txt compliance, bounded retries with backoff, structured logging,
    and a fixture fallback so a single blocked source degrades gracefully
    instead of failing the whole comparison.

    Adding a new retailer = subclassing this and implementing `search()`.
    """

    source_name = "base"
    base_url = ""

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self._robots_cache = {}

    # ---- robots.txt -----------------------------------------------------
    def _robots_allowed(self, url: str) -> bool:
        if not self.config.RESPECT_ROBOTS_TXT:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots_cache:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{origin}/robots.txt")
            try:
                rp.read()
            except Exception:
                # If robots.txt is unreachable, fail closed for safety on
                # write-like actions but allow read-only search here while
                # logging the uncertainty.
                logger.warning("robots.txt unreachable for %s; proceeding cautiously", origin)
                self._robots_cache[origin] = None
            else:
                self._robots_cache[origin] = rp
        rp = self._robots_cache[origin]
        if rp is None:
            return True
        return rp.can_fetch(self.config.USER_AGENT, url)

    # ---- HTTP with retry/backoff -----------------------------------------
    def _get(self, url: str, **kwargs) -> requests.Response:
        if not self._robots_allowed(url):
            raise SourceBlockedError(f"robots.txt disallows fetching {url}")

        last_exc = None
        for attempt in range(1, self.config.MAX_RETRIES + 2):
            try:
                resp = self.session.get(url, timeout=self.config.REQUEST_TIMEOUT, **kwargs)
                if resp.status_code in (403, 429):
                    raise SourceBlockedError(
                        f"{self.source_name} returned {resp.status_code} for {url}"
                    )
                if resp.status_code >= 500:
                    raise ScraperError(f"{self.source_name} server error {resp.status_code}")
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout, ScraperError) as exc:
                last_exc = exc
                if attempt <= self.config.MAX_RETRIES and not isinstance(exc, SourceBlockedError):
                    sleep_for = self.config.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    logger.info(
                        "%s: retrying after error (%s), attempt %d, sleeping %.1fs",
                        self.source_name, exc, attempt, sleep_for,
                    )
                    time.sleep(sleep_for)
                    continue
                raise
        raise last_exc  # pragma: no cover

    # ---- fixture fallback -------------------------------------------------
    def _fixture_path(self):
        return self.config.FIXTURE_DIR / f"{self.source_name}.json"

    @staticmethod
    def _row_key(row):
        return row.get("sku") or row.get("product_url") or row.get("product_name")

    @staticmethod
    def _matches_query(row, query_tokens):
        if not query_tokens:
            return True
        name = (row.get("product_name") or "").lower()
        return all(tok in name for tok in query_tokens)

    def load_fixture(self, query: str = None):
        """Loads the cached snapshot for this source, filtered down to rows
        whose product_name actually matches the searched query. Without
        this filter, a query for a product that was never live-scraped
        (or that live-scraping failed for) would incorrectly return
        whatever unrelated product happened to be cached last -- e.g.
        searching "Samsung" returning cached iPhone offers."""
        path = self._fixture_path()
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        query_tokens = [t for t in (query or "").lower().split() if len(t) >= 2]
        matched = [row for row in data if self._matches_query(row, query_tokens)]

        for row in matched:
            row["is_fixture_fallback"] = True
            row["scraped_at"] = datetime.utcnow().isoformat()
        return matched

    def save_fixture(self, rows):
        """Merge a successful live scrape into the existing cached snapshot
        for this source, keyed by SKU/URL/name, rather than overwriting the
        whole file. This way the cache accumulates known-good data for
        every product that's ever been searched, instead of only ever
        remembering the most recently searched product."""
        path = self._fixture_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)

        by_key = {self._row_key(r): r for r in existing}
        for row in rows:
            clean = {k: v for k, v in row.items() if k not in ("is_fixture_fallback", "_source_error")}
            by_key[self._row_key(clean)] = clean

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(list(by_key.values()), fh, indent=2, default=str)

    # ---- public API ---------------------------------------------------
    def search(self, query: str, storage: str = None, colour: str = None) -> list:
        """Return a list of raw offer dicts. Subclasses implement
        `_search_live`; this wrapper adds the fallback behaviour and never
        lets an exception escape to the caller."""
        try:
            rows = self._search_live(query, storage=storage, colour=colour)
            if rows:
                self.save_fixture(rows)
                return rows
            logger.warning("%s: live scrape returned no rows, using fixture fallback", self.source_name)
        except Exception as exc:
            logger.error("%s: live scrape failed (%s), using fixture fallback", self.source_name, exc)

        if self.config.ALLOW_FIXTURE_FALLBACK:
            return self.load_fixture(query=query)
        return []

    def _search_live(self, query: str, storage: str = None, colour: str = None) -> list:
        raise NotImplementedError
