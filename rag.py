"""
rag.py
SQLite keyword search RAG — mirrors lab rag_search.py pattern.
Searches knowledge_base.db built from Wolfers & Zitzewitz (2006) + platform data.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.db")

# Category → relevant KB categories to prioritize
CATEGORY_ROUTING = {
    "sports":   ["category_sports", "liquidity", "spread_analysis", "platform_fees"],
    "politics": ["category_politics", "liquidity", "spread_analysis", "academic_theory"],
    "finance":  ["category_finance", "spread_analysis", "platform_fees", "academic_theory"],
    "crypto":   ["category_crypto", "liquidity", "spread_analysis", "platform_fees"],
    "all":      ["spread_analysis", "platform_fees", "liquidity", "academic_theory"],
}


def search_knowledge_base(query: str, top_n: int = 3, category: str = None) -> list[dict]:
    """
    Search knowledge base using keyword matching.
    Mirrors rag_search.py from lab exactly — SQL LIKE keyword search.

    Parameters
    ----------
    query : str
        Natural language query
    top_n : int
        Max results to return
    category : str, optional
        If provided, boosts results from matching category

    Returns
    -------
    list[dict]
        {"id", "title", "content", "category"} dicts ordered by relevance
    """
    keywords = [w.strip() for w in query.lower().split() if len(w.strip()) > 2]
    if not keywords:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Relevance score: count keyword hits + category boost
    score_cases = " + ".join(
        f"(CASE WHEN LOWER(title) LIKE '%{kw}%' OR LOWER(content) LIKE '%{kw}%' THEN 1 ELSE 0 END)"
        for kw in keywords
    )

    # Category boost
    cat_boost = ""
    if category and category in CATEGORY_ROUTING:
        preferred = CATEGORY_ROUTING[category]
        cat_cases = " + ".join(
            f"(CASE WHEN category = '{c}' THEN 2 ELSE 0 END)"
            for c in preferred
        )
        cat_boost = f" + ({cat_cases})"

    where_clauses = " OR ".join(
        f"(LOWER(title) LIKE '%{kw}%' OR LOWER(content) LIKE '%{kw}%')"
        for kw in keywords
    )

    sql = f"""
        SELECT id, title, content, category,
               ({score_cases}){cat_boost} AS relevance_score
        FROM documents
        WHERE {where_clauses}
        ORDER BY relevance_score DESC
        LIMIT {top_n}
    """

    rows = cur.execute(sql).fetchall()
    conn.close()

    return [
        {
            "id":       row["id"],
            "title":    row["title"],
            "content":  row["content"],
            "category": row["category"],
        }
        for row in rows
    ]


def format_context(results: list[dict]) -> str:
    """Format search results into prompt-injectable context string."""
    if not results:
        return "No relevant context found in knowledge base."

    lines = ["[Prediction Markets Knowledge Base — Wolfers & Zitzewitz (2006) + Platform Data]\n"]
    for i, doc in enumerate(results, 1):
        lines.append(f"[{i}] {doc['title']} (Category: {doc['category']})")
        lines.append(doc["content"])
        lines.append("")

    return "\n".join(lines)


def retrieve(query: str, top_n: int = 3, category: str = None) -> str:
    """Single call: search + format. Returns ready-to-inject context string."""
    results = search_knowledge_base(query, top_n=top_n, category=category)
    return format_context(results)


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("spread exploitable after fees", "sports"),
        ("political markets efficiency user base", "politics"),
        ("favorite longshot bias low probability", None),
        ("liquidity order book depth Polymarket", "crypto"),
    ]
    for q, cat in tests:
        print(f"\n{'='*60}")
        print(f"Query: '{q}' | Category: {cat}")
        print("="*60)
        print(retrieve(q, top_n=2, category=cat)[:400] + "...")
