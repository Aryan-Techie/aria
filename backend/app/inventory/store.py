"""Where stock is read from.

Two implementations behind one method (`all()`), chosen once at import the
same way app/crm/store.py chooses its lead store:

- MemoryProductStore - the fixtures. Default, and what pytest runs on.
- EspoProductStore   - the live CAriaProduct rows, so a stock figure changed
                       in the browser is true for the next question asked.

Timeout policy
--------------
This runs on the turn path while a customer is waiting to be answered, so the
client here is built with its own SHORT timeout (INVENTORY_TIMEOUT), not the
5s default EspoClient ships with. Five seconds of silence mid-call is worse
than not knowing: Agora's webhook window is finite, and dead air is the one
failure a caller always notices. A slow or dead CRM raises
InventoryUnavailable in well under a second and the tool says "let me confirm
that" instead of stalling.

Field naming
------------
Fields on a CUSTOM entity are NOT c-prefixed. The "c" prefix applies to custom
fields added to a stock entity (Lead -> cAriaUserCount); a field created on
CAriaProduct keeps the name it was given. Verified against this build: the
Metadata tree lists `sku`, and filtering on `cSku` answers
400 "Not existing attribute 'cSku' in where."
"""
from __future__ import annotations

import logging

from app.inventory.fixtures import SEED_PRODUCTS
from app.inventory.models import InventoryUnavailable, Product

logger = logging.getLogger("aria")

# The Espo scope. Custom ENTITIES *are* prefixed - "AriaProduct" is addressed
# as "CAriaProduct" - unlike the fields on them.
ENTITY = "CAriaProduct"

# Enough for a demo catalogue, and small enough that one round trip beats
# per-product lookups: the whole list is fetched and matched in process.
MAX_PRODUCTS = 100


def _from_espo(record: dict) -> Product:
    status = record.get("status") or "in_stock"
    return Product(
        sku=record.get("sku") or record.get("id", ""),
        name=record.get("name") or record.get("sku") or "",
        stock_qty=int(record.get("stockQty") or 0),
        price_usd=record.get("priceUsd"),
        lead_time_days=record.get("leadTimeDays"),
        status=status if status in ("in_stock", "low_stock", "out_of_stock", "discontinued") else "in_stock",
    )


class MemoryProductStore:
    """Fixtures plus whatever's been added since - copied on read so a
    caller cannot mutate the live list by editing a returned Product."""

    def __init__(self) -> None:
        self._products = [p.model_copy() for p in SEED_PRODUCTS]

    def all(self) -> list[Product]:
        return [p.model_copy() for p in self._products]

    def add(self, product: Product) -> Product:
        self._products.append(product)
        return product


class EspoProductStore:
    """Live CAriaProduct rows. Read-only for the AGENT's own tool-calling
    path (check_inventory never writes) - the API user's role otherwise
    grants read only, per scripts/provision_crm.py's ROLE_DATA. add() below
    is a distinct, explicit admin action (the new /api/products endpoint),
    not something the agent can reach mid-call; it will raise EspoCRMError
    if the provisioned role hasn't separately been granted create on
    CAriaProduct - that's a real limitation to close in provision_crm.py,
    not silently worked around here."""

    def __init__(self, client) -> None:
        self._client = client

    def all(self) -> list[Product]:
        from app.crm.espo_client import EspoCRMError

        try:
            rows = self._client.list(ENTITY, max_size=MAX_PRODUCTS)
        except EspoCRMError as exc:
            logger.warning("inventory: EspoCRM read failed (%s)", exc)
            raise InventoryUnavailable(str(exc)) from exc
        return [_from_espo(row) for row in rows]

    def add(self, product: Product) -> Product:
        payload: dict = {
            "sku": product.sku,
            "name": product.name,
            "stockQty": product.stock_qty,
            "status": product.status,
        }
        if product.price_usd is not None:
            payload["priceUsd"] = product.price_usd
        if product.lead_time_days is not None:
            payload["leadTimeDays"] = product.lead_time_days
        # description/category aren't provisioned CAriaProduct fields today
        # (see scripts/provision_crm.py's INVENTORY_FIELDS) - they round-trip
        # fine on the in-memory store, which is what actually runs in dev.
        record = self._client.create(ENTITY, payload)
        return product.model_copy(update={"sku": record.get("sku", product.sku)})


def _build_store():
    """Chosen once at import, mirroring app/crm/store.py.

    The fixtures are the default AND the fallback: if EspoCRM is selected but
    unconfigured, the tool still answers rather than the app failing to boot.
    """
    from app.config import get_settings

    settings = get_settings()
    if settings.crm_backend != "espocrm":
        return MemoryProductStore()

    if not settings.espocrm_api_key:
        logger.warning(
            "CRM_BACKEND=espocrm but ESPOCRM_API_KEY is empty - inventory falls back to fixtures"
        )
        return MemoryProductStore()

    from app.crm.espo_client import EspoClient

    logger.info(
        "Inventory backend: EspoCRM %s at %s (timeout %.2fs)",
        ENTITY,
        settings.espocrm_base_url,
        settings.inventory_timeout_seconds,
    )
    # Its own client, not the lead store's: that one is tuned for writes that
    # may take a moment and must not be cut off. A read that is late is
    # worthless here, so this one gives up fast.
    return EspoProductStore(
        EspoClient(
            settings.espocrm_base_url,
            settings.espocrm_api_key,
            timeout=settings.inventory_timeout_seconds,
        )
    )


product_store = _build_store()
