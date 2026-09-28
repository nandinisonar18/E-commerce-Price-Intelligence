import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import BaseScraper, ScraperError

PRICE_RE = re.compile(r"[\d,]+")


def _to_number(text):
    if not text:
        return None
    match = PRICE_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


class CromaScraper(BaseScraper):
    source_name = "croma"
    base_url = "https://www.croma.com"
    search_url = "https://www.croma.com/searchB?q={query}%3Arelevance&text={query}"

    def _search_live(self, query, storage=None, colour=None):
        full_query = f"{query} {storage or ''}".strip()
        url = self.search_url.format(query=quote_plus(full_query))
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Croma's product grid markup changes fairly often; this selector
        # set targets the current product-tile pattern and is intentionally
        # tolerant (multiple fallback selectors) so small DOM tweaks don't
        # break the whole adapter. If the site markup has moved further,
        # this will legitimately return [] and the base class falls back
        # to the cached fixture snapshot rather than crashing the request.
        tiles = soup.select("li.product-item, div.product-item, div[class*='product-tile']")
        rows = []
        for tile in tiles[:10]:
            name_el = tile.select_one("h3, .product-title, a[title]")
            price_el = tile.select_one(".amount, .new-price, span[class*='price']")
            link_el = tile.select_one("a[href]")
            if not name_el or not price_el:
                continue
            name = name_el.get_text(strip=True) or name_el.get("title", "")
            price = _to_number(price_el.get_text(strip=True))
            if not name or price is None:
                continue
            product_url = link_el["href"] if link_el else None
            if product_url and product_url.startswith("/"):
                product_url = self.base_url + product_url

            rows.append({
                "source": self.source_name,
                "product_name": name,
                "product_url": product_url,
                "currency": "INR",
                "mrp": price,
                "selling_price": price,
                "discount": None,
                "availability": "unknown",
                "seller": "Croma",
                "offer_text": "Bank/EMI offers vary by card issuer; see product page.",
                "offer_type": "bank_emi",
                "emi_available": True,
            })

        if not rows:
            raise ScraperError("croma: no product tiles matched current selectors")
        return rows
