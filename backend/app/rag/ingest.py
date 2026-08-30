"""Loads and chunks the hand-authored knowledge base docs in app/rag/docs/.

Deliberately simple: the corpus is 4 short files, so naive paragraph/section
chunking is sufficient — no chunk-overlap or token-window logic needed.
"""
import json
import re
from pathlib import Path

from pydantic import BaseModel

DOCS_DIR = Path(__file__).parent / "docs"


class Chunk(BaseModel):
    source: str
    text: str


def _chunk_markdown(source: str, text: str) -> list[Chunk]:
    """Split a markdown doc into chunks on level-1/2 headers."""
    sections = re.split(r"\n(?=#{1,2} )", text.strip())
    return [Chunk(source=source, text=s.strip()) for s in sections if s.strip()]


def _chunk_pricing_json(source: str, raw: str) -> list[Chunk]:
    """Turn the structured pricing doc into a few readable text chunks, one per
    tier plus one for billing policy and one per device line, so keyword
    search has real text to match. Tolerant of fields being absent (e.g.
    price_per_seat_monthly vs. price_per_device) rather than requiring an
    exact fixed schema — the pricing doc's shape has already changed once."""
    data = json.loads(raw)
    billing_bits = [f"Billing policy: {data['product']} is billed {data['billing']}."]
    if data.get("annual_discount_percent"):
        billing_bits.append(f"Annual billing discount: {data['annual_discount_percent']}%.")
    if data.get("financing_note"):
        billing_bits.append(data["financing_note"])
    chunks = [Chunk(source=source, text=" ".join(billing_bits))]

    for tier in data.get("tiers", []):
        if tier.get("price_per_seat_monthly") is not None:
            price = f"${tier['price_per_seat_monthly']}/seat/month"
        elif tier.get("price_per_device"):
            price = tier["price_per_device"]
        else:
            price = "custom quote"
        text = (
            f"{tier['name']} tier pricing: {price}, for {tier['included_seats_band']}. "
            f"Features: {', '.join(tier['features'])}."
        )
        if tier.get("note"):
            text += f" Note: {tier['note']}"
        chunks.append(Chunk(source=source, text=text))

    for device in data.get("device_lineup", []):
        text = f"{device['product']} starting price: ${device['starting_price']}."
        if device.get("note"):
            text += f" {device['note']}"
        chunks.append(Chunk(source=source, text=text))

    return chunks


def load_documents() -> list[tuple[str, str]]:
    docs = []
    for path in sorted(DOCS_DIR.iterdir()):
        if path.is_file() and path.suffix in (".md", ".json"):
            docs.append((path.name, path.read_text(encoding="utf-8")))
    return docs


def build_corpus() -> list[Chunk]:
    chunks: list[Chunk] = []
    for source, raw in load_documents():
        if source.endswith(".json"):
            chunks.extend(_chunk_pricing_json(source, raw))
        else:
            chunks.extend(_chunk_markdown(source, raw))
    return chunks
