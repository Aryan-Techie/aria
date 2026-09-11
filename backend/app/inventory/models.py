"""Stock is structured live state, not knowledge-base prose.

Deliberately NOT part of app/rag: the RAG corpus answers "what does this cost
and what does it do", where a near-miss retrieval is survivable. "Do you have
sixty of them" has exactly one right answer at the moment it is asked, it
changes without anyone touching this repo, and being confidently wrong about
it on a live call costs the deal. So it is a real CRM entity (CAriaProduct,
see scripts/provision_crm.py) read through a dedicated tool.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Availability = Literal["in_stock", "low_stock", "out_of_stock", "discontinued"]


class Product(BaseModel):
    sku: str
    name: str
    stock_qty: int = 0
    price_usd: float | None = None
    lead_time_days: int | None = None
    # What the CRM row says. Derived from stock_qty when the row leaves it
    # blank, so a product a person created by hand in the Espo UI without
    # picking an availability still answers correctly.
    status: Availability = "in_stock"
    # Prose, not stock-keeping data - blank for the seeded catalogue, set
    # when a product is added through the admin dashboard so the RAG doc
    # generated for it (app/rag/docs/custom_products.md) has something to say.
    description: str | None = None
    category: str | None = None

    def resolved_status(self) -> Availability:
        if self.status == "discontinued":
            return self.status
        if self.stock_qty <= 0:
            return "out_of_stock"
        if self.stock_qty < 10:
            return "low_stock"
        return "in_stock"

    def can_fulfil(self, quantity: int) -> bool:
        return self.stock_qty >= quantity > 0


class InventoryUnavailable(RuntimeError):
    """The stock system could not be reached in time.

    Raised rather than returning an empty list, because "we have none" and "I
    could not check" are different sentences to say to a customer and only one
    of them is honest.
    """
