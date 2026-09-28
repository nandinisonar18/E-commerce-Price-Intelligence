# E-commerce Price Intelligence

A Flask application that compares smartphone prices, bank offers and EMI across
**Croma, Vijay Sales and Reliance Digital**. Enter a model, storage, colour,
budget, down payment and EMI tenure, and get a ranked comparison with the best
current price, the best price after offers, and the lowest monthly EMI.

## Features
- Parallel source adapters (one per retailer) behind a common interface
- Product/variant matching across inconsistent listing titles
- Strict search: exact model, storage, colour and budget filters
- Effective price and EMI calculated for the selected tenure (standard and no-cost EMI)
- Failure isolation: one blocked source never breaks the search
- Scrape timestamps and crawl history stored in the database
- REST endpoints plus a simple search UI

## How it works
1. `POST /api/search` receives the query and filters.
2. The aggregator runs all source scrapers concurrently.
3. `matcher.py` normalizes titles into one variant ID (brand, model, storage, colour).
4. Filters and budget are applied, then `emi.py` computes effective price and EMI.
5. Results are ranked, saved, and returned as JSON for the UI.

## Project structure
```
app.py                 Flask app and routes
scrapers/              Source adapters (croma, vijaysales, reliancedigital)
services/matcher.py    Title normalization and variant grouping
services/emi.py        EMI and effective-price calculations
services/aggregator.py Orchestrates scraping, matching, ranking, persistence
models.py              Product, Offer, CrawlRun
fixtures/              Cached sample data
scripts/               Fixture generator and pipeline validator
tests/                 Unit and integration tests
```

## EMI assumptions
- Standard EMI: `P·r·(1+r)^n / ((1+r)^n − 1)`, with `r` = annual rate ÷ 12 (default 13%)
- No-cost EMI: financed amount ÷ tenure, and only when the offer covers the selected tenure
- Offers are not stacked automatically

## Endpoints
`GET /` · `POST /api/search` · `GET /api/product/<id>` · `GET /api/offers/<id>` ·
`GET /api/price-history/<id>` · `GET /health`

## Run
See setup below (install requirements, then start the app). Run tests with `pytest`.

## Limitations
- Croma and Reliance Digital load prices with JavaScript, so a plain HTTP scraper
  cannot read them. Reliable live prices need Playwright or the sites' internal APIs.
- When live scraping fails, cached snapshots are used and marked "cached". Most prices
  in the sample data are illustrative; only some Vijay Sales prices are verified.
- Real product-page links exist for iPhone 17 Pro; other rows link to the retailer's search page.
- Scrapers should respect each site's terms and robots.txt.

## Roadmap
- Playwright scrapers for JavaScript-rendered sites
- Bank-offer parsing from each retailer's offers page
- Price-history charts
- Background scraping (Celery/Redis) with caching
-
- ## Quick start (local)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py          # http://127.0.0.1:5000
```

