from app.rag.ingest import build_corpus
from app.rag.retriever import KeywordIndex, top_score


def test_corpus_loads_all_docs():
    chunks = build_corpus()
    sources = {c.source for c in chunks}
    assert sources == {"competitor_comparison.md", "faq.md", "features.md", "pricing.json"}
    assert len(chunks) > 5


def test_search_pricing_query_returns_pricing_content():
    index = KeywordIndex(build_corpus())
    results = index.search("what does the enterprise tier cost", top_k=3)
    assert results
    assert any("Enterprise" in r.text or "enterprise" in r.text.lower() for r in results)


def test_search_competitor_query_returns_comparison_doc():
    index = KeywordIndex(build_corpus())
    results = index.search("how does this compare to a Windows PC fleet", top_k=3)
    assert results
    assert results[0].source == "competitor_comparison.md"


def test_search_irrelevant_query_returns_low_or_no_score():
    index = KeywordIndex(build_corpus())
    # deliberately zero vocabulary overlap with any doc (unlike e.g. "migration",
    # which legitimately appears in the switching-cost content and would score high)
    irrelevant_query = "octopus underwater basket weaving"
    results = index.search(irrelevant_query, top_k=3)
    assert top_score(irrelevant_query) < 0.5
    real_score = index.search("MacBook price", top_k=1)[0].score
    assert not results or results[0].score < real_score
