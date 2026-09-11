from fastapi.testclient import TestClient

from app.main import app
from app.rag import retriever
from app.rag.ingest import DOCS_DIR

client = TestClient(app)
_CUSTOM_DOC = DOCS_DIR / "custom_products.md"


def test_create_product_appears_in_list_and_is_searchable():
    original = _CUSTOM_DOC.read_text(encoding="utf-8")
    try:
        resp = client.post(
            "/api/products",
            json={
                "name": "iPhone Zenith",
                "category": "iPhone",
                "price_usd": 1499,
                "description": "A titanium test-only iPhone variant, satellite-first connectivity.",
                "stock_qty": 12,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "iPhone Zenith"
        assert body["price_usd"] == 1499

        listed = client.get("/api/products").json()
        assert any(p["name"] == "iPhone Zenith" for p in listed)

        # The actual point: findable on the very next question, no restart.
        results = retriever.search("iPhone Zenith satellite connectivity", top_k=3)
        assert any("Zenith" in r.text for r in results)
    finally:
        _CUSTOM_DOC.write_text(original, encoding="utf-8")
        retriever.reset_index()


def test_missing_required_field_is_a_validation_error():
    resp = client.post("/api/products", json={"category": "iPhone", "price_usd": 999})
    assert resp.status_code == 422
