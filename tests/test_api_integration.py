import pytest

from app import create_app
from config import Config
from models import db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # Force every source to fail live and use the checked-in fixtures,
    # so this test is deterministic and needs no network access.
    RESPECT_ROBOTS_TXT = True


@pytest.fixture
def client(monkeypatch):
    app = create_app(TestConfig)

    # Make every scraper's live path fail so the run exercises the fixture
    # fallback path deterministically (no network calls in CI).
    from scrapers.base import BaseScraper

    def fail_live(self, query, storage=None, colour=None):
        raise RuntimeError("live scraping disabled in test")

    monkeypatch.setattr(BaseScraper, "_search_live", fail_live)

    with app.test_client() as client:
        yield client


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_search_requires_query(client):
    resp = client.post("/api/search", json={})
    assert resp.status_code == 400


def test_search_falls_back_to_fixtures_and_returns_ranked_results(client):
    resp = client.post("/api/search", json={
        "query": "iPhone 17 Pro",
        "storage": "256GB",
        "tenure_months": 12,
        "down_payment": 20000,
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["used_fixture_fallback"] is True
    assert len(body["sources_failed"]) == 0  # fixture fallback still counts as "succeeded" data-wise... 
    assert len(body["results"]) >= 1

    top = body["results"][0]
    assert "best_effective_price" in top
    offers = top["offers"]
    assert len(offers) >= 2  # matched across at least 2 of the 3 sources
    # Results should be sorted ascending by effective price.
    prices = [o["effective_price"] for o in offers]
    assert prices == sorted(prices)
    # EMI should be present and labelled as an estimate.
    assert offers[0]["emi_breakdown"]["is_estimate"] is True
    # Every offer returned must actually be an iPhone -- regression guard
    # for the bug where the fixture fallback ignored the query entirely
    # and returned whatever product was cached, regardless of what was
    # searched for.
    for o in offers:
        assert "iphone" in o["product_name"].lower()


def test_fixture_fallback_is_filtered_by_query_not_whatever_is_cached(client):
    """Searching for a different brand must return that brand's cached
    data, not the most-recently-cached/only-cached product."""
    resp = client.post("/api/search", json={"query": "Samsung Galaxy S24 Ultra"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["results"]) >= 1
    for result in body["results"]:
        assert "iphone" not in result["product"]["canonical_name"].lower()
        for offer in result["offers"]:
            assert "samsung" in offer["product_name"].lower() or "galaxy" in offer["product_name"].lower()


def test_query_with_no_cached_match_returns_empty_not_unrelated_products(client):
    resp = client.post("/api/search", json={"query": "Nokia 3310"})
    assert resp.status_code == 200
    body = resp.get_json()
    # No fixture data exists for this query, so results must be empty
    # rather than silently substituting an unrelated cached product.
    assert body["results"] == []


def test_colour_synonym_does_not_leave_stray_words_in_display_name(client):
    """Regression: 'titanium black' was previously stripped in two passes
    ('black' first), leaving a dangling 'Titanium' token in the displayed
    product/model name."""
    resp = client.post("/api/search", json={"query": "Samsung Galaxy S24 Ultra"})
    body = resp.get_json()
    assert len(body["results"]) >= 1
    for result in body["results"]:
        name = result["product"]["canonical_name"]
        assert "titanium" not in name.lower()


def test_storage_filter_matches_when_that_variant_exists(client):
    """256GB and 128GB Samsung variants both exist in the fixtures, so
    requesting one must not silently return the other."""
    resp = client.post("/api/search", json={"query": "Samsung Galaxy S24 Ultra", "storage": "128GB"})
    body = resp.get_json()
    assert not body.get("filter_relaxed")
    assert len(body["results"]) >= 1
    for result in body["results"]:
        assert result["product"]["storage"] == "128GB"


def test_storage_filter_is_strict_and_explains_empty_result(client):
    """Only exactly what was searched is shown: a storage with no listing
    returns no results plus a message naming what IS available."""
    resp = client.post("/api/search", json={"query": "OnePlus 13", "storage": "512GB"})
    body = resp.get_json()
    assert body["results"] == []
    assert "512GB" in body["no_match_message"]
    assert "256GB" in body["no_match_message"]


def test_colour_filter_is_strict_and_any_means_no_filter(client):
    resp = client.post("/api/search", json={"query": "iPhone 17 Pro", "storage": "256GB", "colour": "lavender"})
    assert resp.get_json()["results"] == []
    resp = client.post("/api/search", json={"query": "iPhone 17 Pro", "storage": "256GB", "colour": "any"})
    body = resp.get_json()
    assert len(body["results"]) >= 1
    for r in body["results"]:
        assert r["product"]["storage"] == "256GB"


def test_emi_uses_selected_tenure_for_every_offer(client):
    resp = client.post("/api/search", json={"query": "iPhone 17 Pro", "storage": "256GB", "tenure_months": 24})
    for r in resp.get_json()["results"]:
        for o in r["offers"]:
            assert o["emi_tenure"] == 24


def test_one_source_failing_does_not_break_the_whole_search(client, monkeypatch):
    from scrapers.croma import CromaScraper

    def always_fail(self, query, storage=None, colour=None):
        raise RuntimeError("croma simulated outage")

    # Even if croma's fixture-fallback path itself errors, the whole
    # request must still return usable results from the other sources.
    monkeypatch.setattr(CromaScraper, "load_fixture", lambda self: (_ for _ in ()).throw(RuntimeError("no cache")))

    resp = client.post("/api/search", json={"query": "iPhone 17 Pro"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["results"]) >= 1
