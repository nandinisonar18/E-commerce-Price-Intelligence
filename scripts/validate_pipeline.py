"""Exercises the real matching/filtering/EMI pipeline directly against the
fixtures, without needing Flask-SQLAlchemy (not installable in this sandbox
-- no network egress here). This mirrors exactly what services/aggregator.py
does, minus the DB persistence, so it's a faithful check of the actual
production code paths (matcher.py, emi.py are used unmodified).
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.emi import calculate_emi, effective_price  # noqa: E402
from services.matcher import apply_variant_filters, group_offers_by_variant, variant_matches_query  # noqa: E402

FIXTURE_DIR = PROJECT_ROOT / "fixtures"


def load_fixture_filtered(source, query):
    path = FIXTURE_DIR / f"{source}.json"
    data = json.loads(path.read_text())
    tokens = [t for t in query.lower().split() if len(t) >= 2]
    return [r for r in data if all(t in r.get("product_name", "").lower() for t in tokens)]


def search(query, storage=None, colour=None, budget_min=None, budget_max=None,
           down_payment=0.0, tenure_months=12, interest_rate=13.0):
    raw_offers = []
    for source in ("croma", "vijaysales", "reliancedigital"):
        raw_offers.extend(load_fixture_filtered(source, query))

    if not raw_offers:
        return {"results": [], "filter_relaxed": False}

    grouped = group_offers_by_variant(raw_offers)
    grouped = {v: g for v, g in grouped.items() if variant_matches_query(g["meta"]["canonical_name"], query)}
    grouped, relaxed = apply_variant_filters(grouped, storage=storage, colour=colour)

    results = []
    for vid, group in grouped.items():
        meta = group["meta"]
        offers = []
        for raw in group["offers"]:
            eff = effective_price(raw.get("selling_price") or 0, raw.get("offer_discount") or 0)
            if budget_max is not None and eff > budget_max:
                continue
            if budget_min is not None and eff < budget_min:
                continue
            rate = raw.get("emi_rate") if raw.get("emi_rate") is not None else interest_rate
            if rate <= 0 and raw.get("emi_tenure") and raw["emi_tenure"] != tenure_months:
                rate = interest_rate
            emi = calculate_emi(eff, down_payment, tenure_months, rate)
            offers.append({"source": raw["source"], "product_name": raw["product_name"],
                            "selling_price": raw["selling_price"], "effective_price": eff,
                            "emi_monthly": emi.monthly_emi, "tenure": emi.tenure_months})
        if offers:
            offers.sort(key=lambda o: o["effective_price"])
            results.append({"variant": vid, "meta": meta, "offers": offers})

    results.sort(key=lambda r: r["offers"][0]["effective_price"])
    return {"results": results, "filter_relaxed": bool(relaxed), "relaxed_criteria": relaxed}


def show(title, **kwargs):
    print(f"\n=== {title} ===  args={kwargs}")
    res = search(**kwargs)
    print(f"filter_relaxed={res['filter_relaxed']} relaxed_criteria={res.get('relaxed_criteria')}")
    print(f"{len(res['results'])} variant group(s):")
    for r in res["results"]:
        m = r["meta"]
        cheapest = r["offers"][0]
        print(f"  - {m['canonical_name']}  [{len(r['offers'])} source(s)]  "
              f"best=₹{cheapest['effective_price']:.0f} via {cheapest['source']}  "
              f"EMI≈₹{cheapest['emi_monthly']:.0f}/mo")


if __name__ == "__main__":
    show("Reproduce screenshot: iPhone 17 Pro, 512GB, colour=black",
         query="iphone 17 pro", storage="512GB", colour="black",
         budget_min=30000, budget_max=200000, down_payment=20000)

    show("iPhone 17 Pro, 256GB, no colour filter",
         query="iphone 17 pro", storage="256GB",
         budget_min=30000, budget_max=200000, down_payment=20000)

    show("Budget search: redmi, 10k-30k",
         query="redmi", budget_min=10000, budget_max=30000)

    show("Budget search: samsung, 10k-40k (should surface Galaxy M14/A55, not just S-series)",
         query="samsung", budget_min=10000, budget_max=40000)

    show("Storage filter that legitimately doesn't exist: OnePlus 13, 512GB",
         query="oneplus 13", storage="512GB")

    show("Generic iphone search, no filters",
         query="iphone")

    show("Pixel search",
         query="pixel", budget_min=0, budget_max=100000)
