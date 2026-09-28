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


class RelianceDigitalScraper(BaseScraper):
    source_name = "reliancedigital"
    base_url = "https://www.reliancedigital.in"
    search_url = "https://www.reliancedigital.in/search?q={query}"

    def _search_live(self, query, storage=None, colour=None):
        full_query = f"{query} {storage or ''}".strip()
        url = self.search_url.format(query=quote_plus(full_query))
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        tiles = soup.select("div[class*='sp__product'], div[class*='product-grid'] div[class*='product']")
        rows = []
        for tile in tiles[:10]:
            name_el = tile.select_one("p[class*='title'], h3, a[title]")
            price_el = tile.select_one("span[class*='price'], div[class*='price']")
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
                "seller": "Reliance Digital",
                "offer_text": "Card/EMI offers listed on the all-offers page; validity varies.",
                "offer_type": "card_emi",
                "emi_available": True,
            })

        if not rows:
            raise ScraperError("reliancedigital: no product tiles matched current selectors")
        return rows
