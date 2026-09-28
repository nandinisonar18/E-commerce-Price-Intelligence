"""One-off generator for a much richer seed/fixture catalogue.

Run from the project root: python3 scripts/gen_fixtures.py
Writes fixtures/croma.json, fixtures/vijaysales.json, fixtures/reliancedigital.json.

Why this exists: the original seed data only covered one flagship model per
brand (iPhone 17 Pro, Galaxy S24 Ultra, OnePlus 13) in one or two storage/
colour combinations. That meant almost every search except an exact
"iPhone 17 Pro 128/256GB" query returned nothing, and budget/storage filters
had nothing below ~1,20,000 to filter down to. This generator builds a
catalogue spanning multiple brands, storage tiers and price bands (budget /
mid / flagship) so search, storage filtering, colour filtering and budget
filtering all have real data to work against.
"""
import json
import random
from pathlib import Path
from urllib.parse import quote_plus

random.seed(42)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

SOURCES = ["croma", "vijaysales", "reliancedigital"]
SELLER_NAME = {"croma": "Croma", "vijaysales": "Vijay Sales", "reliancedigital": "Reliance Digital"}
BASE_URL = {
    "croma": "https://www.croma.com",
    "vijaysales": "https://www.vijaysales.com",
    "reliancedigital": "https://www.reliancedigital.in",
}

# The exact same search-URL templates the live scrapers use (scrapers/*.py).
# A fixture row has no way of knowing the real per-product page path (that
# only exists once a live scrape has actually parsed it from the site's
# HTML), so rather than inventing a plausible-looking-but-fake deep link
# that 404s, the fallback/seed data points at a *real, working* search
# results page for that exact product name on that retailer. Once a live
# scrape succeeds for a query, save_fixture() overwrites these rows with
# the real product_url anyway (see scrapers/base.py::search).
SEARCH_URL = {
    "croma": "https://www.croma.com/searchB?q={q}%3Arelevance&text={q}",
    "vijaysales": "https://www.vijaysales.com/search/{q}",
    "reliancedigital": "https://www.reliancedigital.in/search?q={q}",
}


# Real product-page URLs, found via live search of each retailer's own site
# (not guessed). Key: (source, model_name, storage, colour). Any fixture row
# not listed here falls back to the retailer's search-results URL above.
REAL_URLS = {
    # Croma
    ("croma", "Apple iPhone 17 Pro", "256GB", "Deep Blue"): "https://www.croma.com/apple-iphone-17-pro-256gb-deep-blue-/p/317418",
    ("croma", "Apple iPhone 17 Pro", "256GB", "Silver"): "https://www.croma.com/apple-iphone-17-pro-256gb-silver-/p/317415",
    ("croma", "Apple iPhone 17 Pro", "256GB", "Cosmic Orange"): "https://www.croma.com/apple-iphone-17-pro-256gb-cosmic-orange-/p/317417",
    ("croma", "Apple iPhone 17 Pro", "512GB", "Deep Blue"): "https://www.croma.com/apple-iphone-17-pro-512gb-deep-blue-/p/317423",
    ("croma", "Apple iPhone 17 Pro", "512GB", "Silver"): "https://www.croma.com/apple-iphone-17-pro-512gb-silver-/p/317421",
    ("croma", "Apple iPhone 17 Pro", "1TB", "Deep Blue"): "https://www.croma.com/apple-iphone-17-pro-1tb-deep-blue-/p/317429",
    # Vijay Sales
    ("vijaysales", "Apple iPhone 17 Pro", "256GB", "Deep Blue"): "https://www.vijaysales.com/p/P245195/245196/apple-iphone-17-pro-256gb-deep-blue",
    ("vijaysales", "Apple iPhone 17 Pro", "256GB", "Silver"): "https://www.vijaysales.com/p/P245195/245194/apple-iphone-17-pro-256gb-silver",
    ("vijaysales", "Apple iPhone 17 Pro", "256GB", "Cosmic Orange"): "https://www.vijaysales.com/p/P245195/245195/apple-iphone-17-pro-256gb-cosmic-orange",
    ("vijaysales", "Apple iPhone 17 Pro", "512GB", "Deep Blue"): "https://www.vijaysales.com/p/P245195/245202/apple-iphone-17-pro-512gb-deep-blue",
    ("vijaysales", "Apple iPhone 17 Pro", "1TB", "Deep Blue"): "https://www.vijaysales.com/p/P245195/245205/apple-iphone-17-pro-1tb-deep-blue",
    # Reliance Digital
    ("reliancedigital", "Apple iPhone 17 Pro", "256GB", "Deep Blue"): "https://www.reliancedigital.in/product/apple-iphone-17-pro-256-gb-deep-blue-mff5yc-9388030",
    ("reliancedigital", "Apple iPhone 17 Pro", "256GB", "Silver"): "https://www.reliancedigital.in/product/apple-iphone-17-pro-256-gb-silver-mff5yc-9388031",
    ("reliancedigital", "Apple iPhone 17 Pro", "256GB", "Cosmic Orange"): "https://www.reliancedigital.in/product/apple-iphone-17-pro-256-gb-cosmic-orange-mff5yc-9388032",
}

# Prices read directly from Vijay Sales' live iPhone 17 listing page:
# (selling_price, mrp). Only these are real; every other price in the
# fixtures is illustrative seed data.
VERIFIED_VIJAY_PRICES = {
    ("Apple iPhone 17 Pro", "256GB", "Cosmic Orange"): (129490.0, 134900.0),
    ("Apple iPhone 17 Pro", "512GB", "Deep Blue"): (154900.0, 154900.0),
    ("Apple iPhone 17 Pro", "1TB", "Deep Blue"): (174900.0, 174900.0),
}


def _search_link(source, product_name):
    return SEARCH_URL[source].format(q=quote_plus(product_name))
BANKS = ["HDFC Bank", "ICICI Bank", "Axis Bank", "SBI Card", "Kotak Bank"]

# (model_name, [(storage, [colours])], base_price_for_lowest_storage, price_step_per_storage_tier, brand_slug)
CATALOGUE = [
    # ---- Apple flagship / recent ----
    ("Apple iPhone 17 Pro", [("256GB", ["Deep Blue", "Silver", "Cosmic Orange"]),
                              ("512GB", ["Deep Blue", "Silver"]),
                              ("1TB", ["Deep Blue"])], 134900, 16000, "ip17p"),
    ("Apple iPhone 17", [("128GB", ["Black", "White", "Gold", "Green"]),
                          ("256GB", ["Black", "White", "Green"])], 79900, 10000, "ip17"),
    ("Apple iPhone 16", [("128GB", ["Black", "White", "Gold", "Green"]),
                          ("256GB", ["Black", "White"])], 69900, 10000, "ip16"),
    ("Apple iPhone 15", [("128GB", ["Black", "Gold", "Green"])], 59900, 10000, "ip15"),
    ("Apple iPhone SE", [("64GB", ["Black", "White", "Gold"]), ("128GB", ["Black", "White"])], 39900, 6000, "ipse"),

    # ---- Samsung flagship / mid ----
    # (128GB kept as the lowest tier -- existing regression tests assert it
    # exists and is not silently substituted for another storage.)
    ("Samsung Galaxy S24 Ultra", [("128GB", ["Titanium Black"]),
                                   ("256GB", ["Titanium Black", "Titanium Gray", "Titanium Violet"]),
                                   ("512GB", ["Titanium Black", "Titanium Gray"]),
                                   ("1TB", ["Titanium Black"])], 109999, 10000, "gs24u"),
    ("Samsung Galaxy S23", [("128GB", ["Black", "Cream", "Green"]),
                             ("256GB", ["Black", "Cream"])], 64999, 8000, "gs23"),
    ("Samsung Galaxy M14", [("128GB", ["Black", "Gold", "Green"])], 13999, 2000, "gm14"),
    ("Samsung Galaxy A55", [("128GB", ["Black", "White", "Violet"]),
                             ("256GB", ["Black", "White"])], 34999, 5000, "ga55"),

    # ---- OnePlus ----
    # (512GB deliberately NOT offered -- an existing regression test asserts
    # that requesting a storage tier with no real listing relaxes the
    # filter with an explicit note rather than silently substituting
    # another storage.)
    ("OnePlus 13", [("256GB", ["Black", "Silver"])], 64999, 6000, "op13"),
    ("OnePlus Nord 4", [("128GB", ["Gray", "White"]), ("256GB", ["Gray", "White"])], 29999, 4000, "opn4"),

    # ---- Xiaomi / Redmi / Poco ----
    ("Redmi Note 13 Pro", [("128GB", ["Black", "White", "Violet"]),
                            ("256GB", ["Black", "White"])], 24999, 3000, "rn13p"),
    ("Redmi 13C", [("128GB", ["Black", "Green", "White"])], 9999, 1500, "r13c"),
    ("Poco X6 Pro", [("256GB", ["Black", "White", "Gray"])], 26999, 3000, "px6p"),

    # ---- Google ----
    ("Google Pixel 9", [("128GB", ["Black", "White", "Green"]),
                         ("256GB", ["Black", "White"])], 79999, 9000, "gp9"),
    ("Google Pixel 8", [("128GB", ["Black", "White"])], 59999, 7000, "gp8"),

    # ---- Others ----
    ("Nothing Phone 2a", [("128GB", ["White", "Black"])], 23999, 3000, "np2a"),
    ("Motorola Edge 50", [("128GB", ["Black", "Green", "Gray"])], 22999, 3000, "me50"),
    ("Realme 13 Pro", [("128GB", ["Black", "Gold", "Green"])], 25999, 3000, "r13p"),
]

OFFER_TEMPLATES = [
    ("bank_emi", "No-cost EMI on {bank} Credit Cards for {t} month tenure.", 0.0, 0),
    ("bank_emi", "Flat Rs.{disc} instant discount on {bank} Credit Card EMI transactions.", 13.0, None),
    ("card_emi", "Card/EMI offer: Rs.{disc} off with {bank} Debit/Credit Card EMI.", 13.0, None),
    ("exchange", "Exchange offer up to Rs.{disc} on select older models.", 13.0, None),
    ("none", "Standard pricing, no additional bank offer active currently.", 13.0, 0),
]

AVAILABILITY = ["in_stock", "in_stock", "in_stock", "out_of_stock", "limited_stock"]


def build_rows():
    per_source = {s: [] for s in SOURCES}
    for model_name, storage_lines, base_price, step, slug in CATALOGUE:
        for tier_idx, (storage, colours) in enumerate(storage_lines):
            tier_price = base_price + step * tier_idx
            for colour in colours:
                # Not every source stocks every variant -- pick 2 or 3 of the
                # 3 sources at random (but deterministically, via seeded RNG)
                # so the catalogue reads like a real, imperfectly-overlapping
                # multi-retailer market rather than 3 mirrored price lists.
                n_sources = random.choice([2, 2, 3, 3, 3])
                chosen_sources = random.sample(SOURCES, n_sources)
                for source in chosen_sources:
                    # +/- up to 4% price variance per retailer
                    variance = random.uniform(-0.04, 0.03)
                    selling_price = round((tier_price * (1 + variance)) / 10) * 10
                    mrp = round(selling_price * random.uniform(1.02, 1.08) / 10) * 10
                    discount_val = int(mrp - selling_price)

                    offer_type, text_template, emi_rate, fixed_offer_discount = random.choice(OFFER_TEMPLATES)
                    bank = random.choice(BANKS)
                    tenure = random.choice([3, 6, 9, 12])
                    offer_discount = fixed_offer_discount
                    if offer_discount is None:
                        offer_discount = int(round(selling_price * random.uniform(0.01, 0.04) / 10) * 10)
                    offer_text = text_template.format(bank=bank, t=tenure, disc=offer_discount)

                    colour_slug = colour.lower().replace(" ", "-")
                    sku = f"{source.upper()[:4]}-{slug.upper()}-{storage}-{colour_slug[:4].upper()}"
                    product_name_variants = {
                        "croma": f"{model_name} ({storage}, {colour})",
                        "vijaysales": f"{model_name} {storage} {colour}",
                        "reliancedigital": f"{model_name} ({storage}) {colour}",
                    }
                    name_for_source = product_name_variants[source]
                    row = {
                        "source": source,
                        "product_name": name_for_source,
                        "product_url": REAL_URLS.get((source, model_name, storage, colour))
                        or _search_link(source, name_for_source),
                        "sku": sku,
                        "currency": "INR",
                        "mrp": float(mrp),
                        "selling_price": float(selling_price),
                        "discount": float(discount_val),
                        "availability": random.choice(AVAILABILITY),
                        "seller": SELLER_NAME[source],
                        "rating": round(random.uniform(3.9, 4.8), 1),
                        "review_count": random.randint(40, 1800),
                        "offer_text": offer_text,
                        "offer_type": offer_type,
                        "bank": bank if offer_type in ("bank_emi", "card_emi") else None,
                        "offer_discount": float(offer_discount),
                        "emi_available": True,
                        "emi_tenure": tenure,
                        "emi_rate": emi_rate,
                    }
                    if source == "vijaysales" and (model_name, storage, colour) in VERIFIED_VIJAY_PRICES:
                        sp, mp = VERIFIED_VIJAY_PRICES[(model_name, storage, colour)]
                        row["selling_price"], row["mrp"], row["discount"] = sp, mp, mp - sp
                    per_source[source].append(row)
    return per_source


def main():
    per_source = build_rows()
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for source, rows in per_source.items():
        path = FIXTURE_DIR / f"{source}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
        print(f"{source}: wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
