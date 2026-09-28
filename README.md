# E-commerce Price Intelligence Platform (Smartphones)

A Flask app that takes a mobile model + optional preferences, scrapes
Croma, Vijay Sales and Reliance Digital, matches the same product/variant
across sources, normalizes price/offer data, calculates EMI scenarios, and
shows a ranked comparison with the best deal explained.

## Quick start (local)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py          # http://127.0.0.1:5000
```

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build     # http://127.0.0.1:5000
```

## Run the tests

```bash
pytest -q
```

Tests are fully offline (they force the fixture-fallback path with
`monkeypatch`), so CI never depends on live retailer sites being reachable
or unblocked.

## Live demo notes (read this before presenting)

Croma, Vijay Sales and Reliance Digital all run bot-detection (403/429
responses, occasional interstitials) and change their HTML fairly often.
That is expected, real-world behaviour for retail scraping targets — not a
bug in this project. The app is built to be honest about it and to keep
working anyway:

- Each adapter tries a **live** scrape first, respecting `robots.txt`,
  with bounded retries/backoff.
- If a source is blocked, times out, or its selectors no longer match the
  current page layout, that adapter falls back to the **last known-good
  snapshot** for that source (`fixtures/<source>.json`), and the response
  clearly flags `is_fixture_fallback: true` per offer plus
  `sources_failed` / `used_fixture_fallback` at the top level.
- Every successful *live* scrape overwrites that fixture, so the fallback
  is always "yesterday's real data," not permanently fake data.
- One source failing never breaks the comparison — this is asserted by
  `tests/test_api_integration.py::test_one_source_failing_does_not_break_the_whole_search`.

**If you want to demo pure live scraping**, run it from a network/IP that
isn't already rate-limited, and expect that CSS selectors in
`scrapers/croma.py`, `scrapers/vijaysales.py`, `scrapers/reliancedigital.py`
may need small updates if the sites' markup has changed since this was
written (Sept 2026) — the selectors are written with multiple fallback
patterns for exactly this reason, and each adapter degrades to its fixture
rather than crashing if none match.

## Architecture

```
app.py                 Flask routes / API
config.py               Settings (env-driven)
models.py               SQLAlchemy: Product, Offer, CrawlRun
scrapers/
  base.py                Session, robots.txt check, retry/backoff, fixture fallback
  croma.py, vijaysales.py, reliancedigital.py   One adapter per retailer
services/
  matcher.py             Free-text -> normalized variant_id (cross-source matching)
  emi.py                 EMI math, kept separate from scraped facts
  aggregator.py           Orchestrates: concurrent scrape -> match -> EMI -> rank -> persist
templates/, static/       Minimal frontend (vanilla JS, fetches /api/search)
fixtures/                 Per-source fallback snapshots (auto-updated on live success)
tests/                    Unit tests (EMI, matching) + integration test (API, offline)
```

Adding a 4th retailer = one new file in `scrapers/` implementing
`_search_live()`, registered in `scrapers/__init__.py`. Nothing else
changes.

### Why offers, not just products, are the base table

`Offer` rows are append-only and timestamped, so the same table doubles as
price history (`GET /api/price-history/<product_id>`) without a separate
history table. `Product` only stores the normalized variant identity.

### Product matching approach

Rule-based normalization (`services/matcher.py`): extracts storage (regex),
colour (synonym lookup table), and a cleaned model string, then builds a
stable `variant_id`. This is transparent and testable for a single
category (smartphones). A multi-category version would likely add a fuzzy
fallback (e.g. token-set ratio) behind the same `normalize_variant()`
function signature.

### EMI logic

`services/emi.py` implements standard reducing-balance EMI. When a
source's fixture/offer explicitly states a no-cost EMI (`emi_rate: 0`),
the calculator switches to a straight-line financed-amount/tenure split
with zero interest — it never assumes no-cost EMI on its own. Every EMI
value returned by the API is nested under `emi_breakdown` with
`"is_estimate": true`, and offers are **not** assumed to be
combinable/stackable; only the source-stated `offer_discount` is applied
to get `effective_price`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Search UI |
| `POST /api/search` | `{query, storage?, colour?, budget_min?, budget_max?, down_payment?, tenure_months?, interest_rate?, sources?}` -> ranked comparison |
| `GET /api/product/<id>` | Normalized product/variant |
| `GET /api/offers/<id>` | All offers for a product |
| `GET /api/price-history/<id>` | Price-over-time for a product |
| `GET /api/crawl/<crawl_id>` | Metadata for a past crawl run (which sources succeeded/failed) |
| `GET /health` | Health check |

## Assumptions & limitations

- Search is **strict**: storage, colour, budget and exact model are hard
  filters. Searching "iPhone 17 Pro / 256GB / lavender" returns only that
  combination; if nothing matches, the UI says why and lists the storages
  and colours that do exist for the model (nothing is silently substituted).
  "Any" in storage/colour means no filter. A search naming a model number
  ("iPhone 17 Pro") excludes siblings such as "Pro Max" or the base model.
- EMI is always calculated for the **tenure selected in the form**. A
  source's no-cost EMI offer only counts when it covers that tenure;
  otherwise standard interest applies and the row shows a note explaining it.
- Fixture rows' `product_url` points at that retailer's **live search
  results page** for the exact listing name (the same URL template the
  live scraper itself uses), not a guessed product-page deep link. A
  fixture row has no way to know the real per-product URL path — that's
  only known once a live scrape has actually parsed it out of the site's
  HTML — so a fabricated deep link would just 404. The UI labels these
  "search on site ↗" (vs. "source ↗" for a genuinely live-scraped exact
  product page) so it's clear which kind of link you're getting.
- The bundled `fixtures/*.json` snapshots cover ~18 models across Apple,
  Samsung, OnePlus, Xiaomi/Redmi/Poco, Google, Nothing, Motorola and
  Realme, spanning ~₹10,000–₹1,70,000 and multiple storage/colour
  variants per model, each listed by 2–3 of the 3 sources — so budget,
  storage and colour filters all have real data to filter against instead
  of only the one flagship phone the original seed data shipped with.
  Regenerate/extend this catalogue with `python3 scripts_gen_fixtures.py`
  (edit the `CATALOGUE` list at the top of that file to add more
  models/variants).
- Deal score is intentionally simple and transparent: it rewards lower
  effective price and higher rating, scaled against the max effective
  price seen in that comparison set — not a black-box ML ranking.
- No JavaScript rendering (Playwright) is used in the base submission;
  all 3 required adapters work against server-rendered/search HTML. A
  Playwright fallback for genuinely JS-only pages is listed as an
  optional advanced feature and is not implemented here.
- Availability is reported as `"unknown"` by the live scrapers when the
  page doesn't clearly expose stock status in the selectors matched;
  fixture data shows the richer `in_stock`/`out_of_stock` fields to
  illustrate the intended shape once selectors are tuned to current
  markup.
- SQLite is used by default (per the test's "SQLite acceptable"); set
  `DATABASE_URL` to a Postgres DSN to switch.

## Sample output

Run a search and check `GET /api/crawl/<crawl_id>` plus the `/api/search`
JSON response for a self-contained example — every field in section 5 of
the spec (`product_name`, `sku`, `offer_text`, `emi_monthly`,
`scraped_at`, etc.) is present on each offer object.
