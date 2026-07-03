"""
search_index.py
Splits the knowledge base (data.json) into small searchable chunks and
ranks them against a query using TF-IDF + cosine similarity — a real
semantic-ish search over "everything", implemented in pure Python so it
needs nothing heavier than what's already in requirements.txt.

Pipeline:
    1. CHUNK   -> build_index() walks knowledge_base / faq / scraped_pages
                  and slices them into ~120-word chunks with source labels.
    2. INDEX   -> each chunk gets a TF-IDF vector; the corpus IDF table is
                  cached in chunks.json alongside the chunks themselves.
    3. SEARCH  -> search(query, top_k) vectorizes the query with the same
                  IDF table and ranks chunks by cosine similarity.

Rebuild the index any time data.json changes:
    python search_index.py
or call build_index() after scraper.py updates the knowledge base.
"""

import json
import math
import os
import re
from collections import Counter

from src.tools import utils

import os as _os
INDEX_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "data", "chunks.json")
CHUNK_WORD_SIZE = 120
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "and", "or", "in", "on", "at", "for", "with", "by", "as",
    "it", "this", "that", "these", "those", "i", "you", "he", "she", "we",
    "they", "them", "his", "her", "its", "our", "your", "their", "from",
    "but", "not", "so", "if", "than", "then", "there", "here", "which",
    "who", "what", "when", "where", "how", "do", "does", "did", "will",
    "would", "can", "could", "should", "may", "might", "have", "has", "had",
}


def _tokenize(text: str):
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _chunk_text(text: str, source: str, size: int = CHUNK_WORD_SIZE):
    words = text.split()
    chunks = []
    for i in range(0, len(words), size):
        piece = " ".join(words[i:i + size]).strip()
        if piece:
            chunks.append({"text": piece, "source": source})
    return chunks


def _collect_raw_chunks():
    data = utils.load_data()

    # data/data.json in this project ships as a flat list of {"question","answer"}
    # objects rather than the nested {"knowledge_base": {...}, "faq": [...]} schema
    # this indexer was originally written for. Support both.
    if isinstance(data, list):
        raw_chunks = []
        for item in data:
            raw_chunks += _chunk_text(
                f"Q: {item.get('question', '')} A: {item.get('answer', '')}", "FAQ"
            )
        return raw_chunks

    kb = data.get("knowledge_base", {})
    raw_chunks = []

    institute = kb.get("institute", {})
    if institute:
        raw_chunks += _chunk_text(
            f"{institute.get('name')} is located at {institute.get('address')}. "
            f"Phone: {', '.join(institute.get('phone', []))}. Email: {institute.get('email')}. "
            f"Website: {institute.get('website')}. Facebook: {institute.get('facebook')}.",
            "Institute Info",
        )

    if kb.get("about"):
        raw_chunks += _chunk_text(kb["about"], "About")
    if kb.get("vision"):
        raw_chunks += _chunk_text(kb["vision"], "Vision")
    if kb.get("mission"):
        raw_chunks += _chunk_text(kb["mission"], "Mission")
    if kb.get("commitment"):
        raw_chunks += _chunk_text(kb["commitment"], "Commitment")

    for course in kb.get("courses_offered", []):
        raw_chunks += _chunk_text(
            f"{course.get('code')}: {course.get('full_name')}. More info: {course.get('url')}.",
            f"Course · {course.get('code')}",
        )

    leadership = kb.get("leadership", {})
    for role, info in leadership.items():
        raw_chunks += _chunk_text(
            f"{info.get('title')}: {info.get('name')}. \"{info.get('message', '')}\"",
            f"Leadership · {info.get('title')}",
        )

    for post in kb.get("recent_posts", []):
        raw_chunks += _chunk_text(post, "Recent Post")

    for item in data.get("faq", []):
        raw_chunks += _chunk_text(
            f"Q: {item['question']} A: {item['answer']}", "FAQ"
        )

    for page in kb.get("scraped_pages", []):
        raw_chunks += _chunk_text(page.get("text", ""), f"Scraped · {page.get('title', page.get('url'))}")

    return raw_chunks


def build_index():
    """Rebuilds chunks.json from the current data.json. Returns the chunk list."""
    raw_chunks = _collect_raw_chunks()

    doc_freq = Counter()
    tokenized = []
    for c in raw_chunks:
        toks = _tokenize(c["text"])
        tokenized.append(toks)
        for w in set(toks):
            doc_freq[w] += 1

    n_docs = max(len(raw_chunks), 1)
    idf = {w: math.log((n_docs + 1) / (df + 1)) + 1 for w, df in doc_freq.items()}

    chunks = []
    for c, toks in zip(raw_chunks, tokenized):
        tf = Counter(toks)
        total = max(len(toks), 1)
        vector = {w: (count / total) * idf.get(w, 0.0) for w, count in tf.items()}
        chunks.append({"text": c["text"], "source": c["source"], "vector": vector})

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"idf": idf, "chunks": chunks}, f, ensure_ascii=False)

    return chunks


def _load_index():
    if not os.path.exists(INDEX_FILE):
        build_index()
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _cosine(vec_a: dict, vec_b: dict) -> float:
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[w] * vec_b[w] for w in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values())) or 1e-9
    norm_b = math.sqrt(sum(v * v for v in vec_b.values())) or 1e-9
    return dot / (norm_a * norm_b)


def search(query: str, top_k: int = 3, min_score: float = 0.08):
    """Returns up to top_k chunks [{'text','source','score'}] relevant to
    query, ranked by TF-IDF cosine similarity. Empty list if nothing clears
    min_score."""
    index = _load_index()
    idf = index["idf"]
    chunks = index["chunks"]
    if not chunks:
        return []

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    tf = Counter(q_tokens)
    total = max(len(q_tokens), 1)
    q_vector = {w: (count / total) * idf.get(w, 0.0) for w, count in tf.items()}

    scored = []
    for c in chunks:
        score = _cosine(q_vector, c["vector"])
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [
        {"text": c["text"], "source": c["source"], "score": round(score, 3)}
        for score, c in scored[:top_k]
        if score >= min_score
    ]
    return results


def format_context(results: list) -> str:
    if not results:
        return ""
    parts = [f"[{r['source']}] {r['text']}" for r in results]
    return "\n\n".join(parts)


if __name__ == "__main__":
    n = len(build_index())
    print(f"Built search index: {n} chunks -> {INDEX_FILE}")
