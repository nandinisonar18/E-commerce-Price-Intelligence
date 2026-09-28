from services.matcher import group_offers_by_variant, normalize_variant


def test_same_variant_different_naming_matches():
    a = normalize_variant("Apple iPhone 17 Pro (256GB, Deep Blue)")
    b = normalize_variant("iPhone 17 Pro 256GB Deep Blue")
    c = normalize_variant("iPhone 17 Pro - 256 GB - Deep Blue")
    assert a["variant_id"] == b["variant_id"] == c["variant_id"]


def test_different_storage_does_not_match():
    a = normalize_variant("Apple iPhone 17 Pro (256GB, Deep Blue)")
    b = normalize_variant("Apple iPhone 17 Pro (128GB, Deep Blue)")
    assert a["variant_id"] != b["variant_id"]


def test_multiword_colour_synonym_does_not_leave_stray_tokens():
    # Regression: replacing "black" before "titanium black" left a
    # dangling "titanium" token in the model/display name.
    meta = normalize_variant("Samsung Galaxy S24 Ultra (256GB, Titanium Black)")
    assert meta["colour"] == "Black"
    assert "titanium" not in meta["canonical_name"].lower()
    assert "titanium" not in (meta["model"] or "").lower()


def test_apple_iphone_and_iphone_alone_match_the_same_variant():
    # Regression: "Apple iPhone 17 Pro" had an extra "apple" token that
    # "iPhone 17 Pro" (no "Apple" prefix) didn't, producing two different
    # variant_ids for the same physical product across sources.
    a = normalize_variant("Apple iPhone 17 Pro (256GB, Deep Blue)")
    b = normalize_variant("iPhone 17 Pro 256GB Deep Blue")
    assert a["variant_id"] == b["variant_id"]


def test_grouping_collects_multiple_sources_under_one_variant():
    offers = [
        {"source": "croma", "product_name": "Apple iPhone 17 Pro (256GB, Deep Blue)"},
        {"source": "vijaysales", "product_name": "iPhone 17 Pro 256GB Deep Blue"},
        {"source": "reliancedigital", "product_name": "Apple iPhone 17 Pro (256GB) Deep Blue"},
    ]
    grouped = group_offers_by_variant(offers)
    assert len(grouped) == 1
    only_group = next(iter(grouped.values()))
    assert len(only_group["offers"]) == 3
