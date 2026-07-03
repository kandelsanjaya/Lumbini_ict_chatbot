"""
src/tools/utils.py
Small, dependency-free helpers shared across the app:
  - data.json read/write (used by the scraper & search index tools)
  - chat export to Markdown / JSON (wired into the sidebar in app.py)

Note: greeting detection, knowledge-base search, and LLM summarization
live in `src/core/rag.py` (the more advanced FAISS + Groq pipeline) —
this module intentionally stays lightweight and free of API calls.
"""

import json
import os
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE = os.path.join(BASE_DIR, "data", "data.json")


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"knowledge_base": {}, "faq": [], "greetings": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def log_interaction_to_json(username: str, role: str, content: str):
    """Append a lightweight mirror of every message into data.json under 'interaction_log'."""
    data = load_data()
    log = data.setdefault("interaction_log", [])
    log.append({
        "user": username,
        "role": role,
        "content": content,
        "timestamp": datetime.datetime.now().isoformat(),
    })
    data["interaction_log"] = log[-500:]
    save_data(data)


def export_chat_as_markdown(messages: list, title: str = "Chat Export") -> str:
    lines = [f"# {title}", f"_Exported on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_", ""]
    for m in messages:
        role = "🧑 You" if m["role"] == "user" else "🤖 Assistant"
        lines.append(f"**{role}:**\n\n{m['content']}\n")
    return "\n".join(lines)


def export_chat_as_json(messages: list) -> str:
    return json.dumps(messages, indent=2, ensure_ascii=False)
