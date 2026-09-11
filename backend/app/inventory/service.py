"""Turning what the customer called a product into the row that holds its stock.

The model passes through whatever the caller said - "the iPhone", "MacBook
Airs", "ipad pro 11", "IPAD-10". None of those are the record's name, so a
plain dictionary lookup answers "we don't stock that" for a product sitting
right there. Matching happens here, in process, over the whole (small)
catalogue the store fetched in one round trip.

Why the token weighting
-----------------------
A flat word-overlap score matched "Surface Pro" to iPad Pro M4 11-inch -
found on a live read, not in review - because "pro" is half of what was said.
Quoting our iPad stock to someone asking about a competitor's laptop is worse
than admitting we do not carry it, so every query word is weighted by how
rare it is in the catalogue: "surface" appears nowhere and therefore counts
for a lot unmatched, while "pro" is a modifier several products share. That
drops Surface Pro to 0.42 while every real phrasing scores 0.72 or better.
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from app.inventory.models import Product
from app.inventory.store import product_store

# Measured against the seeded catalogue: real phrasings ("macbook", "the 11
# inch iPad Pro", "ipads") score 0.72-1.0, while competitor and nonsense
# queries ("Surface Pro", "Thinkpad X1", "Chromebook") top out at 0.42.
MATCH_THRESHOLD = 0.55
# A second product this close behind the winner is a genuine ambiguity
# ("iPad" is two rows), and she should ask which rather than pick one.
AMBIGUITY_MARGIN = 0.08

_PLURALS = re.compile(r"(?<=[a-z])s\b")


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    # "macbook airs" and "ipads" are the same product as the singular.
    return _PLURALS.sub("", text)


def _tokens(text: str) -> list[str]:
    return [t for t in _normalise(text).split() if t]


def _weights(products: list[Product]) -> dict[str, float]:
    """Inverse document frequency over the catalogue.

    A word in every product name says nothing about which one is meant; a word
    in none of them (a competitor's brand) is the strongest possible signal
    that we do not stock what was asked for.
    """
    total = len(products)
    seen: dict[str, int] = {}
    for product in products:
        for token in set(_tokens(product.name)) | set(_tokens(product.sku)):
            seen[token] = seen.get(token, 0) + 1
    return {token: math.log((total + 1) / (1 + count)) + 1 for token, count in seen.items()}


def _weight(token: str, weights: dict[str, float], total: int) -> float:
    # Unknown to the catalogue: weighted as if it appeared in nothing, which
    # is exactly what it is.
    return weights.get(token, math.log(total + 1) + 1)


def score(product: Product, query: str, weights: dict[str, float], total: int) -> float:
    """0-1, how well a row answers to what the caller called it."""
    q = _normalise(query)
    if not q:
        return 0.0

    sku = _normalise(product.sku)
    name = _normalise(product.name)
    if q in (sku, name):
        return 1.0
    # "IPAD-10" spoken back by the model, or a name given in full.
    if q in sku or sku in q:
        return 0.95

    query_tokens = _tokens(query)
    product_tokens = set(_tokens(product.name)) | set(_tokens(product.sku))
    weighted_total = sum(_weight(t, weights, total) for t in query_tokens)
    matched = sum(_weight(t, weights, total) for t in query_tokens if t in product_tokens)
    coverage = matched / weighted_total if weighted_total else 0.0

    # Catches misspellings and run-together speech ("mac book air") that token
    # matching misses. Discounted, because a string-similar name is much
    # weaker evidence than the actual words.
    fuzzy = SequenceMatcher(None, q, name).ratio() * 0.8
    return max(coverage, fuzzy)


def rank(query: str, products: list[Product]) -> list[tuple[Product, float]]:
    weights = _weights(products)
    total = len(products)
    scored = [(p, score(p, query, weights, total)) for p in products]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def in_stock_alternatives(exclude_sku: str, *, store=None, limit: int = 3) -> list[Product]:
    """Products we could actually ship instead of the one they asked for.

    Handed to the model rather than left to it. Told only "offer a model we do
    have now", a live turn offered the customer an iPhone 15 Pro - a product
    with no row in this catalogue at all. Inventing a product to console
    someone about the one that is out of stock is exactly the failure this
    whole tool exists to prevent, so the alternatives are named here.
    """
    products = (store or product_store).all()
    available = [
        p for p in products if p.sku != exclude_sku and p.stock_qty > 0 and p.status != "discontinued"
    ]
    available.sort(key=lambda p: p.stock_qty, reverse=True)
    return available[:limit]


def find(query: str, *, store=None) -> tuple[Product | None, list[Product]]:
    """Best match plus the near-misses worth offering instead.

    Never raises for a miss - a miss is a real answer ("we don't carry that")
    and gets alternatives to offer. It DOES let InventoryUnavailable through:
    not knowing is not the same as having none, and the caller of this
    function has to say a different sentence for each.
    """
    products = (store or product_store).all()
    if not products:
        return None, []

    scored = rank(query, products)
    best, best_score = scored[0]
    if best_score < MATCH_THRESHOLD:
        # Nothing matched. Offer the catalogue rather than a dead end.
        return None, [p for p, _ in scored[:3]]

    contenders = [
        p for p, s in scored[1:] if s >= MATCH_THRESHOLD and best_score - s <= AMBIGUITY_MARGIN
    ]
    return best, contenders
