"""Normalizes free-text product names from different retailers into a
stable variant key so the same physical product/variant can be grouped
across sources despite naming differences like:

    "Apple iPhone 17 Pro (256GB, Deep Blue)"
    "Apple iPhone 17 Pro 256GB Deep Blue"
    "iPhone 17 Pro - 256 GB - Deep Blue"

or, for another brand:

    "Samsung Galaxy S24 Ultra (256GB) Titanium Black"
    "Samsung Galaxy S24 Ultra 256GB Titanium Black 5G"

This is deliberately rule-based (regex + lookup tables) rather than fuzzy
ML matching: it's transparent, fast, testable, and good enough for a
smartphone catalogue spanning multiple brands. A production system with
many categories would likely add a fuzzy-matching fallback (e.g.
token-set ratio) behind the same `normalize_variant()` interface.

Brand/model extraction is intentionally generic (word-set based) rather
than hardcoded per brand, so a new brand works out of the box as long as
its listings use recognisable words consistently -- add an entry to
BRAND_KEYWORDS only to get a nicer canonical brand label, not because
matching requires it.
"""

import re

STORAGE_RE = re.compile(r"(\d+)\s*(GB|TB)", re.IGNORECASE)

# Canonical colour names -> accepted synonyms/spellings seen across retailers
COLOUR_SYNONYMS = {
    "deep blue": ["deep blue", "blue"],
    "silver": ["silver", "white silver"],
    "black": ["black", "space black", "jet black", "phantom black", "titanium black"],
    "natural titanium": ["natural titanium", "titanium natural"],
    "gold": ["gold"],
    "orange": ["orange", "cosmic orange"],
    "gray": ["gray", "grey", "titanium gray", "titanium grey"],
    # "titanium violet" must be listed explicitly (not just "violet"), same
    # reasoning as "titanium black"/"titanium gray" below: otherwise
    # stripping only the shorter "violet" token leaves a dangling
    # "titanium" word in the display name.
    "violet": ["violet", "lavender", "titanium violet"],
    "green": ["green"],
    "cream": ["cream"],
    "white": ["white"],
}

# Known brand keywords -> canonical brand display name. Only used to make
# the "brand" field look nice; matching itself doesn't depend on this list.
BRAND_KEYWORDS = {
    "iphone": "Apple", "apple": "Apple",
    "galaxy": "Samsung", "samsung": "Samsung",
    "oneplus": "OnePlus",
    "redmi": "Xiaomi", "xiaomi": "Xiaomi", "poco": "Xiaomi",
    "pixel": "Google", "google": "Google",
    "vivo": "Vivo", "oppo": "Oppo", "realme": "Realme",
    "nothing": "Nothing", "motorola": "Motorola", "moto": "Motorola",
}

# Words that carry no product-identity signal and would otherwise fracture
# matching between sources that include/omit them inconsistently (e.g. one
# retailer writes "5G" in the title and another doesn't).
NOISE_WORDS = {"5g", "4g", "with", "new", "brand", "only", "smartphone", "mobile", "phone"}


def _extract_storage(text: str):
    match = STORAGE_RE.search(text)
    if not match:
        return None
    value, unit = match.groups()
    return f"{value}{unit.upper()}"


def _extract_colour(text: str):
    lowered = text.lower()
    for canonical, synonyms in COLOUR_SYNONYMS.items():
        for syn in synonyms:
            if syn in lowered:
                return canonical
    return None


# Flattened, longest-first list of every colour synonym across all
# canonicals. Order matters here: if we replaced "black" before "titanium
# black", the standalone "black" match would consume part of the phrase
# first and "titanium" would be left stranded as a stray token (a real bug
# this project hit -- "Titanium Black" produced a dangling "Titanium").
_ALL_COLOUR_SYNONYMS_LONGEST_FIRST = sorted(
    {syn for syns in COLOUR_SYNONYMS.values() for syn in syns}, key=len, reverse=True
)


def _extract_brand(tokens):
    for tok in tokens:
        if tok in BRAND_KEYWORDS:
            return BRAND_KEYWORDS[tok]
    return tokens[0].title() if tokens else "Unknown"


def _clean_tokens(text: str):
    """Strips storage/colour/punctuation/noise words, returning the
    remaining words in original order (used for the display model name)."""
    lowered = text.lower()
    lowered = STORAGE_RE.sub(" ", lowered)
    for syn in _ALL_COLOUR_SYNONYMS_LONGEST_FIRST:
        lowered = lowered.replace(syn, " ")
    lowered = re.sub(r"[()\-,]", " ", lowered)
    tokens = [t for t in lowered.split() if t and t not in NOISE_WORDS]
    return tokens


def normalize_variant(raw_name: str, storage_hint: str = None, colour_hint: str = None):
    """Returns a dict describing the normalized variant plus a
    `variant_id` string that is stable across sources for the same
    model/storage/colour combination, regardless of brand.
    """
    storage = _extract_storage(raw_name) or (storage_hint.upper().replace(" ", "") if storage_hint else None)
    colour = _extract_colour(raw_name) or (colour_hint.lower() if colour_hint else None)

    tokens = _clean_tokens(raw_name)
    brand = _extract_brand(tokens)
    model_display = " ".join(tokens).strip()

    # The matching key ignores word order (so "Galaxy S24 Ultra" and
    # "S24 Ultra Galaxy" -- a real-world naming inconsistency -- still
    # group together) and collapses brand aliases (one source writes
    # "Apple iPhone 17 Pro", another just "iPhone 17 Pro") to the same
    # canonical brand token before hashing, so both produce the same key.
    match_tokens = {BRAND_KEYWORDS.get(t, t).lower() for t in tokens}
    model_key = "-".join(sorted(match_tokens)) or "unknown-model"

    key_parts = [model_key, storage or "unknown-storage", colour or "any-colour"]
    variant_id = re.sub(r"\s+", "-", "-".join(key_parts).strip("-"))

    return {
        "variant_id": variant_id,
        "brand": brand,
        "model": model_display.title() if model_display else None,
        "storage": storage,
        "colour": colour.title() if colour else None,
        "canonical_name": f"{model_display.title() if model_display else raw_name} {storage or ''} {colour.title() if colour else ''}".strip(),
    }


def canonical_colour(user_colour: str):
    """Maps whatever the user typed ("lavender", "Titanium Black", "blue")
    to our canonical colour name so it compares against listing colours.
    Returns None for empty/"any" (no colour filter requested)."""
    if not user_colour:
        return None
    wanted = user_colour.strip().lower()
    if wanted in ("", "any", "all", "selected", "any colour", "any color"):
        return None
    for canonical, synonyms in COLOUR_SYNONYMS.items():
        if wanted == canonical or wanted in synonyms:
            return canonical
    # Unknown colour word: fall back to a plain substring test on the text
    return wanted


def apply_variant_filters(grouped: dict, storage: str = None, colour: str = None):
    """STRICT filter: keeps only variants matching the requested storage and
    colour. Nothing is relaxed or substituted -- if you search 256GB you only
    ever see 256GB.

    Returns (filtered_grouped, unmet) where `unmet` lists the criteria that
    matched nothing (so the caller can say exactly why the result is empty
    and what *is* available), e.g. ["lavender colour"].
    """
    unmet = []

    if storage and storage.strip().lower() not in ("", "any"):
        wanted_storage = storage.lower().replace(" ", "")
        by_storage = {
            vid: g for vid, g in grouped.items()
            if g["meta"]["storage"] and g["meta"]["storage"].lower() == wanted_storage
        }
        if not by_storage:
            unmet.append(f"{storage} storage")
        grouped = by_storage

    wanted_colour = canonical_colour(colour)
    if wanted_colour:
        by_colour = {
            vid: g for vid, g in grouped.items()
            if g["meta"]["colour"] and wanted_colour in g["meta"]["colour"].lower()
        }
        if not by_colour:
            unmet.append(f"{colour} colour")
        grouped = by_colour

    return grouped, unmet


# Words that turn one phone into a *different* phone ("iPhone 17" vs
# "iPhone 17 Pro" vs "iPhone 17 Pro Max").
_MODEL_QUALIFIERS = {"pro", "max", "plus", "ultra", "mini", "air", "fe", "lite", "se", "e"}


def variant_matches_query(canonical_name: str, query: str) -> bool:
    """When the search names a specific model (contains a number, e.g.
    "iphone 17 pro"), only show that exact model: a search for "iPhone 17
    Pro" must not return "iPhone 17 Pro Max", and "iPhone 17" must not
    return "iPhone 17 Pro". Broad searches like "samsung" are unaffected."""
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not any(ch.isdigit() for tok in q_tokens for ch in tok):
        return True
    name_tokens = set(re.findall(r"[a-z0-9]+", canonical_name.lower()))
    return (name_tokens & _MODEL_QUALIFIERS) <= (q_tokens & _MODEL_QUALIFIERS)


def group_offers_by_variant(raw_offers: list) -> dict:
    """Given raw offer dicts from any number of sources, returns
    {variant_id: {"meta": {...}, "offers": [raw_offer, ...]}}.
    """
    grouped = {}
    for offer in raw_offers:
        meta = normalize_variant(
            offer.get("product_name", ""),
            storage_hint=offer.get("storage_hint"),
            colour_hint=offer.get("colour_hint"),
        )
        vid = meta["variant_id"]
        if vid not in grouped:
            grouped[vid] = {"meta": meta, "offers": []}
        grouped[vid]["offers"].append(offer)
    return grouped
