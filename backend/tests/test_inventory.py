import pytest

from app.inventory import service as inventory_service
from app.inventory import store as inventory_store
from app.inventory.models import InventoryUnavailable, Product
from app.sessions.models import SessionState
from app.tools import executor


def _session() -> SessionState:
    return SessionState(session_id="sess-inv", mem0_user_id="sess-inv")


# --- matching --------------------------------------------------------------


@pytest.mark.parametrize(
    "spoken,expected_sku",
    [
        ("iPhone 15", "IPHONE-15"),
        ("iphone", "IPHONE-15"),
        ("MacBook Airs", "MBA-M3-13"),
        ("macbook air 13 inch", "MBA-M3-13"),
        ("IPAD-10", "IPAD-10"),
        ("iPad Pro", "IPADPRO-M4-11"),
        ("the 11 inch iPad Pro", "IPADPRO-M4-11"),
        ("macbook", "MBA-M3-13"),
    ],
)
def test_matches_what_a_caller_would_actually_say(spoken, expected_sku):
    product, _ = inventory_service.find(spoken)
    assert product is not None and product.sku == expected_sku


@pytest.mark.parametrize(
    "not_ours",
    # "Surface Pro" is the regression: a flat word-overlap score matched it to
    # iPad Pro M4 11-inch on a live read, because "pro" is half of what was
    # said. Quoting our stock for a competitor's laptop is worse than saying
    # we do not carry it.
    ["Surface Pro", "Surface Pro 9", "Dell XPS", "Galaxy S24", "Thinkpad X1", "Chromebook"],
)
def test_products_we_do_not_stock_are_a_miss_not_a_wrong_row(not_ours):
    product, alternatives = inventory_service.find(not_ours)
    assert product is None, f"{not_ours} matched {product.name if product else None}"
    assert alternatives, "a miss must still offer what we do stock"


def test_ambiguous_query_reports_the_other_contender():
    """'iPad' is two products. Picking one silently quotes stock for a product
    the customer was not asking about."""
    product, alternatives = inventory_service.find("iPad")
    assert product is not None
    assert alternatives


# --- espo mapping ----------------------------------------------------------


def test_espo_row_maps_with_unprefixed_field_names():
    """Fields on a CUSTOM entity are not c-prefixed - `sku`, not `cSku`."""
    product = inventory_store._from_espo(
        {
            "id": "abc",
            "name": "iPhone 15",
            "sku": "IPHONE-15",
            "stockQty": 0,
            "priceUsd": 799.0,
            "leadTimeDays": 21,
            "status": "out_of_stock",
        }
    )
    assert product.sku == "IPHONE-15"
    assert product.stock_qty == 0
    assert product.resolved_status() == "out_of_stock"


def test_status_is_derived_when_the_row_leaves_it_blank():
    product = inventory_store._from_espo({"name": "X", "sku": "X-1", "stockQty": 0})
    assert product.resolved_status() == "out_of_stock"
    thin = inventory_store._from_espo({"name": "Y", "sku": "Y-1", "stockQty": 4})
    assert thin.resolved_status() == "low_stock"


# --- the tool --------------------------------------------------------------


def test_in_stock_answer_carries_the_exact_number():
    result = executor.dispatch("check_inventory", {"product": "iPad 10th gen"}, _session())
    assert result["found"] is True
    assert result["units_in_stock"] == 240
    assert result["unit_price_usd"] == 349.0


def test_out_of_stock_answer_carries_the_lead_time():
    result = executor.dispatch("check_inventory", {"product": "iPhone 15"}, _session())
    assert result["availability"] == "out_of_stock"
    assert result["units_in_stock"] == 0
    assert result["lead_time_days"] == 21
    assert "lead time" in result["guidance"]


def test_quantity_shortfall_is_reported_not_rounded_up():
    result = executor.dispatch(
        "check_inventory", {"product": "iPad Pro M4 11-inch", "quantity": 500}, _session()
    )
    assert result["can_fulfil_now"] is False
    assert result["units_in_stock"] == 60


def test_quantity_that_fits_is_confirmed():
    result = executor.dispatch(
        "check_inventory", {"product": "MacBook Air M3 13-inch", "quantity": 40}, _session()
    )
    assert result["can_fulfil_now"] is True


def test_unreachable_stock_system_never_answers_in_or_out_of_stock(monkeypatch):
    """The failure that matters: a CRM that is down must not become 'we have
    none'. She has to say she will confirm."""

    def boom(*_args, **_kwargs):
        raise InventoryUnavailable("timeout")

    monkeypatch.setattr(inventory_service, "find", boom)
    result = executor.dispatch("check_inventory", {"product": "iPhone 15"}, _session())
    assert result["error"] == "inventory_unavailable"
    assert result["available"] is None
    assert "units_in_stock" not in result


def test_espo_store_raises_rather_than_returning_an_empty_catalogue():
    from app.crm.espo_client import EspoCRMError

    class DeadClient:
        def list(self, *_args, **_kwargs):
            raise EspoCRMError("GET /CAriaProduct -> timeout")

    with pytest.raises(InventoryUnavailable):
        inventory_store.EspoProductStore(DeadClient()).all()


def test_products_are_copied_so_a_caller_cannot_mutate_the_seed_set():
    store = inventory_store.MemoryProductStore()
    store.all()[0].stock_qty = -1
    assert all(p.stock_qty >= 0 for p in store.all())


def test_unknown_product_tool_payload_offers_what_we_stock():
    result = executor.dispatch("check_inventory", {"product": "Surface Pro 9"}, _session())
    assert result["found"] is False
    assert result["we_stock"]


def test_product_can_fulfil_rejects_zero_quantity():
    assert Product(sku="A", name="A", stock_qty=5).can_fulfil(0) is False


def test_out_of_stock_names_real_alternatives_not_invented_ones():
    """The live failure this guards: told only to 'offer a model we do have',
    the model offered a customer an iPhone 15 Pro - a product with no row in
    the catalogue. The alternatives must be named in the payload, and every
    one of them must be a product we actually hold."""
    result = executor.dispatch("check_inventory", {"product": "iPhone 15"}, _session())
    assert result["availability"] == "out_of_stock"
    instead = result["in_stock_instead"]
    assert instead, "an out-of-stock answer must name what we can ship"

    catalogue = {p.name for p in inventory_store.MemoryProductStore().all()}
    for option in instead:
        assert option["product"] in catalogue
        assert option["units_in_stock"] > 0
    assert "iPhone 15" not in [o["product"] for o in instead]
    assert "Offer NOTHING that is not on that list" in result["guidance"]
