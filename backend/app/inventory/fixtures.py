"""Fallback stock, used when CRM_BACKEND=memory (the default, and what the
test suite runs on) so the tool works without Docker.

Kept in step with SEED_PRODUCTS in scripts/provision_crm.py - same SKUs, same
numbers, iPhone 15 at zero on purpose so the out-of-stock path is reachable
without editing anything.
"""
from app.inventory.models import Product

SEED_PRODUCTS: list[Product] = [
    Product(sku="IPAD-10", name="iPad 10th gen", stock_qty=240, price_usd=349.0, lead_time_days=3),
    Product(sku="IPADPRO-M4-11", name="iPad Pro M4 11-inch", stock_qty=60, price_usd=999.0, lead_time_days=7),
    Product(sku="MBA-M3-13", name="MacBook Air M3 13-inch", stock_qty=85, price_usd=1099.0, lead_time_days=5),
    Product(sku="IPHONE-15", name="iPhone 15", stock_qty=0, price_usd=799.0, lead_time_days=21, status="out_of_stock"),
]
