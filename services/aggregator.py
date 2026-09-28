import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from models import CrawlRun, Offer, Product, db
from scrapers import SCRAPER_REGISTRY
from services.emi import calculate_emi, effective_price
from services.matcher import apply_variant_filters, group_offers_by_variant, variant_matches_query

logger = logging.getLogger("price_intel.aggregator")


def _run_one_source(source_name, scraper_cls, config, query, storage, colour):
    scraper = scraper_cls(config)
    try:
        rows = scraper.search(query, storage=storage, colour=colour)
        return source_name, rows, None
    except Exception as exc:  # noqa: BLE001 - a source must never crash the run
        logger.exception("%s: unrecoverable error", source_name)
        return source_name, [], str(exc)


def run_search(
    config,
    query: str,
    storage: str = None,
    colour: str = None,
    budget_min: float = None,
    budget_max: float = None,
    down_payment: float = 0.0,
    tenure_months: int = 12,
    interest_rate: float = 13.0,
    sources=None,
):
    """Runs all (or a chosen subset of) source adapters concurrently,
    matches the results into variants, computes effective price and EMI,
    ranks them, and persists everything. Returns a JSON-ready dict.

    Partial failures are expected and handled: if 1 of 3 sources errors or
    is blocked, the other 2 still produce a usable comparison.
    """
    sources = sources or list(SCRAPER_REGISTRY.keys())
    crawl = CrawlRun(query=query, sources_requested=",".join(sources))
    db.session.add(crawl)
    db.session.commit()

    raw_offers = []
    succeeded, failed = [], []

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_SCRAPES) as pool:
        futures = {
            pool.submit(_run_one_source, name, SCRAPER_REGISTRY[name], config, query, storage, colour): name
            for name in sources
            if name in SCRAPER_REGISTRY
        }
        for future in as_completed(futures):
            source_name, rows, error = future.result()
            if error and not rows:
                failed.append(source_name)
            else:
                succeeded.append(source_name)
            for row in rows:
                row["_source_error"] = error
            raw_offers.extend(rows)

    crawl.sources_succeeded = ",".join(succeeded)
    crawl.sources_failed = ",".join(failed)
    crawl.finished_at = datetime.utcnow()
    db.session.commit()

    if not raw_offers:
        return {
            "crawl_id": crawl.id,
            "query": query,
            "sources_succeeded": succeeded,
            "sources_failed": failed,
            "results": [],
            "warning": "No offers could be retrieved from any source.",
        }

    grouped = group_offers_by_variant(raw_offers)

    # Only the exact model searched (not Pro/Max/Plus siblings).
    grouped = {vid: g for vid, g in grouped.items()
               if variant_matches_query(g["meta"]["canonical_name"], query)}

    # Strict storage/colour filtering: show only what was asked for.
    available = {
        "storages": sorted({g["meta"]["storage"] for g in grouped.values() if g["meta"]["storage"]}),
        "colours": sorted({g["meta"]["colour"] for g in grouped.values() if g["meta"]["colour"]}),
    }
    grouped, unmet = apply_variant_filters(grouped, storage=storage, colour=colour)

    results = []
    for variant_id, group in grouped.items():
        meta = group["meta"]

        product = Product.query.filter_by(variant_id=variant_id).first()
        if not product:
            product = Product(
                variant_id=variant_id,
                brand=meta["brand"],
                model=meta["model"],
                storage=meta["storage"],
                colour=meta["colour"],
                canonical_name=meta["canonical_name"],
            )
            db.session.add(product)
            db.session.flush()

        variant_offers = []
        for raw in group["offers"]:
            eff_price = effective_price(raw.get("selling_price") or 0, raw.get("offer_discount") or 0)

            if budget_max is not None and eff_price > budget_max:
                continue
            if budget_min is not None and eff_price < budget_min:
                continue

            # EMI is always computed for the tenure the user selected -- not
            # whatever tenure each offer happens to advertise. A no-cost
            # (0%) offer only counts if it covers the selected tenure;
            # otherwise standard interest applies and we say so.
            emi_rate = raw.get("emi_rate")
            offer_tenure = raw.get("emi_tenure")
            emi_note = None
            if emi_rate is not None and emi_rate <= 0 and offer_tenure and offer_tenure != tenure_months:
                emi_note = (f"No-cost EMI on this offer is only for {offer_tenure} months; "
                            f"{tenure_months}-month EMI is at standard {interest_rate:g}% interest.")
                emi_rate = interest_rate
            emi = calculate_emi(
                price=eff_price,
                down_payment=down_payment,
                tenure_months=tenure_months,
                annual_rate_percent=emi_rate if emi_rate is not None else interest_rate,
            )

            offer = Offer(
                product_id=product.id,
                crawl_run_id=crawl.id,
                source=raw.get("source"),
                product_url=raw.get("product_url"),
                product_name=raw.get("product_name"),
                sku=raw.get("sku"),
                currency=raw.get("currency", "INR"),
                mrp=raw.get("mrp"),
                selling_price=raw.get("selling_price"),
                discount=raw.get("discount"),
                availability=raw.get("availability", "unknown"),
                seller=raw.get("seller"),
                rating=raw.get("rating"),
                review_count=raw.get("review_count"),
                offer_text=raw.get("offer_text"),
                offer_type=raw.get("offer_type"),
                bank=raw.get("bank"),
                offer_discount=raw.get("offer_discount"),
                emi_available=raw.get("emi_available", False),
                emi_tenure=emi.tenure_months,
                emi_rate=emi.annual_rate_percent,
                emi_monthly=emi.monthly_emi,
                effective_price=eff_price,
                is_fixture_fallback=raw.get("is_fixture_fallback", False),
            )
            db.session.add(offer)
            variant_offers.append((offer, emi, emi_note))

        if not variant_offers:
            continue

        prices = [o.effective_price for o, _, _ in variant_offers if o.effective_price is not None]
        max_price = max(prices) if prices else 1

        offer_dicts = []
        for offer, emi, emi_note in variant_offers:
            score = 100.0
            if max_price:
                score = round(100 * (1 - (offer.effective_price / max_price)) + 
                              (offer.rating or 0) * 2, 2)
            offer.deal_score = score
            d = offer.to_dict()
            d["emi_breakdown"] = {
                "financed_amount": emi.financed_amount,
                "down_payment": emi.down_payment,
                "total_repayment": emi.total_repayment,
                "total_interest": emi.total_interest,
                "is_no_cost_emi": emi.is_no_cost_emi,
                "is_estimate": True,
                "note": emi_note,
            }
            offer_dicts.append(d)

        offer_dicts.sort(key=lambda d: d["effective_price"] or float("inf"))

        results.append({
            "product": product.to_dict(),
            "offers": offer_dicts,
            "best_effective_price": offer_dicts[0]["effective_price"] if offer_dicts else None,
            "best_source": offer_dicts[0]["source"] if offer_dicts else None,
        })

    db.session.commit()

    results.sort(key=lambda r: r["best_effective_price"] or float("inf"))

    response = {
        "crawl_id": crawl.id,
        "query": query,
        "sources_requested": sources,
        "sources_succeeded": succeeded,
        "sources_failed": failed,
        "used_fixture_fallback": any(o.get("is_fixture_fallback") for o in raw_offers),
        "results": results,
    }

    if not results:
        reasons = []
        if unmet:
            reasons.append(f"No listing found for {' / '.join(unmet)}.")
            if available["storages"] or available["colours"]:
                reasons.append(
                    "Available for this model: "
                    + (f"storage {', '.join(available['storages'])}" if available["storages"] else "")
                    + ("; " if available["storages"] and available["colours"] else "")
                    + (f"colours {', '.join(available['colours'])}" if available["colours"] else "")
                    + ".")
        elif budget_min is not None or budget_max is not None:
            reasons.append("Listings exist for this model but none fall inside your budget range.")
        else:
            reasons.append("No listing matches this search.")
        response["no_match_message"] = " ".join(reasons)
        response["available_options"] = available

    return response
