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


class VijaySalesScraper(BaseScraper):
    source_name = "vijaysales"
    base_url = "https://www.vijaysales.com"
    search_url = "https://www.vijaysales.com/search/{query}"

    def _search_live(self, query, storage=None, colour=None):
        full_query = f"{query} {storage or ''}".strip()
        url = self.search_url.format(query=quote_plus(full_query))
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "html.parser")

        tiles = soup.select("div.p-item, div[class*='product-box'], div[class*='product-card']")
        rows = []
        for tile in tiles[:10]:
            name_el = tile.select_one("h3, .p-title, a[title]")
            price_el = tile.select_one(".price, span[class*='price'], .p-price")
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
                "seller": "Vijay Sales",
                "offer_text": "Bank EMI discount schemes advertised on category bank-offers page.",
                "offer_type": "bank_emi",
                "emi_available": True,
            })

        if not rows:
            raise ScraperError("vijaysales: no product tiles matched current selectors")
        return rows
