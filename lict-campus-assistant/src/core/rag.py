"""
rag.py — Retrieval-Augmented Generation pipeline (Groq-powered), extended with:

    - Content moderation: harmful/unsafe messages are intercepted BEFORE any
      retrieval or generation call and answered with a safe, fixed refusal
      instead of being sent to the LLM ("terminate" the normal flow).
    - Image fetching: messages like "show me an image of X" / "picture of X"
      are detected and resolved to a real image URL instead of going through
      the text pipeline.
    - Case-sensitive matching boost: exact-case matches on capitalized terms
      (acronyms, proper nouns) in the knowledge base get a small similarity
      boost so e.g. "HR" vs "hr" can be told apart when it matters.
    - Situation-aware tone: simple sentiment detection nudges the system
      prompt to be more supportive/motivating when the user sounds stressed,
      sad, or discouraged, and more neutral/direct otherwise.

Pipeline stages:
    0. MODERATE  -> is_harmful() blocks unsafe requests before anything else runs.
    1. RETRIEVE  -> search_knowledge_base() does dense vector search over data.json
                    via FAISS + sentence-transformers embeddings.
    2. FALLBACK  -> if KB confidence is below threshold, web_search() pulls fresh
                    context from Tavily instead.
    3. AUGMENT   -> build_prompt() merges retrieved context + chat history + the
                    new question + detected tone into a single grounded prompt.
    4. GENERATE  -> generate_answer() calls Groq's LLM API with the augmented
                    prompt.

This file is self-contained and runnable: it loads API keys from a .env file,
builds the pipeline, and drops you into an interactive command-line chat loop.

Setup:
    pip install faiss-cpu sentence-transformers tavily-python groq python-dotenv requests

.env file (same directory as this script):
    GROQ_API_KEY=gsk_your_key_here
    TAVILY_API_KEY=tvly_your_key_here

Run:
    python rag.py
"""

import ipaddress
import json
import os
import re
import socket
import sys
from urllib.parse import urlparse

import numpy as np
import faiss
import requests
from bs4 import BeautifulSoup

from sentence_transformers import SentenceTransformer
from tavily import TavilyClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; env vars can be set another way

SIMILARITY_THRESHOLD = 0.65
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
GROQ_MODEL_NAME = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was deprecated by Groq (June 2026)
CASE_MATCH_BOOST = 0.03  # small nudge applied when a capitalized query term exactly matches case in a doc


class RagPipeline:
    """Wraps the embedder, FAISS index, and the Groq API client as one reusable object."""

    def __init__(
        self,
        groq_key: str = None,
        tavily_key: str = None,
        data_path: str = "data.json",
    ):
        if not groq_key:
            raise ValueError("groq_key is required (GROQ_API_KEY)")

        self.embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self.tavily = TavilyClient(api_key=tavily_key) if tavily_key else None
        self.documents, self.raw_data = self._load_data(data_path)
        self.index = self._build_index(self.documents)
        self.data_path = data_path

        from groq import Groq
        self.groq = Groq(api_key=groq_key)

    # ---------------- Loading & indexing ----------------

    @staticmethod
    def _load_data(path):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f)
            return [], []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        docs = []
        for item in data:
            docs.append(f"Question:\n{item['question']}\n\nAnswer:\n{item['answer']}")
        return docs, data

    def _build_index(self, documents):
        if not documents:
            return None

        vectors = self.embedder.encode(documents, normalize_embeddings=True)
        vectors = np.array(vectors).astype("float32")
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        return index

    def add_to_knowledge_base(self, question: str, answer: str, data_path: str = None):
        data_path = data_path or self.data_path
        self.raw_data.append({"question": question, "answer": answer})
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(self.raw_data, f, indent=2, ensure_ascii=False)

        self.documents.append(f"Question:\n{question}\n\nAnswer:\n{answer}")
        self.index = self._build_index(self.documents)

    # ---------------- 0. MODERATE ----------------

    def moderate(self, text: str):
        """Returns (blocked: bool, reason: str | None, message: str | None)."""
        return moderate_text(text)

    # ---------------- IMAGE REQUESTS ----------------

    def maybe_fetch_image(self, text: str):
        """If the message is an image request, returns a dict with the image
        URL and the resolved query; otherwise returns None."""
        query = detect_image_request(text)
        if not query:
            return None
        url = fetch_image_url(query)
        return {"query": query, "url": url}

    # ---------------- URL FETCH + SUMMARIZE ----------------

    def maybe_fetch_url(self, text: str):
        """If the message contains a URL, fetches it securely and returns a
        dict with the page title, a short extracted-text preview, and a
        Groq-generated summary; otherwise returns None."""
        url = extract_url(text)
        if not url:
            return None

        ok, reason = is_url_safe(url)
        if not ok:
            return {
                "url": url,
                "error": f"That URL can't be fetched ({reason}) — for security, only public http(s) pages are allowed.",
            }

        try:
            page = fetch_url_content(url)
        except Exception as e:
            return {"url": url, "error": f"Couldn't fetch that page: {e}"}

        if not page["text"]:
            return {"url": url, "error": "Fetched the page, but couldn't find readable text content on it."}

        prompt = (
            "Summarize the following webpage content in 4-6 clear sentences, in your own words, "
            "for someone who hasn't read it. Don't copy long verbatim passages.\n\n"
            f"Page title: {page['title']}\n\nContent:\n{page['text'][:6000]}"
        )
        summary = self.generate_answer(prompt)

        return {
            "url": url,
            "title": page["title"],
            "summary": summary,
            "error": None,
        }

    # ---------------- 1. RETRIEVE ----------------

    def search_knowledge_base(self, query: str, top_k: int = 1):
        if self.index is None or not self.documents:
            return 0.0, ""

        q = self.embedder.encode([query], normalize_embeddings=True)
        q = np.array(q).astype("float32")
        scores, idxs = self.index.search(q, top_k)
        best_idx = idxs[0][0]
        score = float(scores[0][0])

        # Case-sensitive boost: if a capitalized token from the query
        # (likely an acronym or proper noun, e.g. "HR", "IT", "LMS") appears
        # with the exact same casing in the matched document, nudge the score
        # up slightly so exact-case terminology is preferred over a generic
        # lowercase match.
        capitalized_terms = re.findall(r"\b[A-Z]{2,}\b", query)
        if capitalized_terms:
            doc_text = self.documents[best_idx]
            if any(term in doc_text for term in capitalized_terms):
                score = min(1.0, score + CASE_MATCH_BOOST)

        return score, self.documents[best_idx]

    # ---------------- 2. FALLBACK ----------------

    def web_search(self, query: str, max_results: int = 3) -> str:
        if not self.tavily:
            return "(Web search is unavailable — no TAVILY_API_KEY configured.)"
        result = self.tavily.search(query=query, max_results=max_results)
        content = ""
        for item in result.get("results", []):
            content += item.get("content", "") + "\n\n"
        return content

    # ---------------- combined retrieval step ----------------

    def retrieve(self, query: str):
        score, kb_context = self.search_knowledge_base(query)

        if score > SIMILARITY_THRESHOLD:
            return kb_context, "Knowledge Base", score
        else:
            web_context = self.web_search(query)
            return web_context, "Web Search", score

    # ---------------- 3. AUGMENT ----------------

    @staticmethod
    def build_prompt(question: str, context: str, history: list, lang_name: str, user_name: str = None):
        history_block = ""
        if history:
            turns = []
            for h in history[-6:]:
                role = "User" if h["role"] == "user" else "Assistant"
                turns.append(f"{role}: {h['content']}")
            history_block = "Recent conversation so far:\n" + "\n".join(turns) + "\n\n"

        name_line = f"The user's name is {user_name}. Address them naturally and warmly when appropriate.\n" if user_name else ""

        detected = detect_input_language(question)
        if detected == "nepali_romanized":
            language_instruction = (
                "The user is typing in Romanized Nepali (Nepali words spelled with English/Roman letters, "
                "e.g. \"k xa\", \"sanchai xau\", \"thik xu\", \"ramro cha\"). "
                "Reply ONLY in Romanized Nepali, in the same casual, friendly texting style — "
                "do NOT switch to English and do NOT use Devanagari script. "
                "Match the user's tone: short, warm, natural, like chatting with a friend."
            )
        elif detected == "nepali_devanagari":
            language_instruction = (
                "The user is typing in Nepali (Devanagari script). "
                "Reply ONLY in Nepali using Devanagari script, in a warm, natural, conversational tone."
            )
        else:
            language_instruction = f"Respond in this language: {lang_name}."

        tone = detect_tone(question)
        if tone == "discouraged":
            tone_instruction = (
                "The user's message suggests they may be feeling stressed, discouraged, tired, or down. "
                "Open with a brief, genuine, warm acknowledgement of that before answering — be encouraging "
                "and supportive without being over-the-top or dismissive of the actual question. "
                "Then answer their question clearly and helpfully."
            )
        elif tone == "frustrated":
            tone_instruction = (
                "The user's message suggests some frustration. Be calm, clear, and solution-focused — "
                "acknowledge the frustration briefly, then get straight to a helpful, accurate answer."
            )
        elif tone == "positive":
            tone_instruction = (
                "The user's message has a positive, upbeat tone. Match that energy lightly while staying useful."
            )
        else:
            tone_instruction = "Respond in a clear, warm, professional tone suited to the question."

        return f"""You are a helpful, friendly, interactive multilingual AI assistant with access to retrieved context — like a ChatGPT-style companion, but focused on answering HR questions accurately and chatting naturally otherwise.

{name_line}{language_instruction}
{tone_instruction}
Always reply in the SAME language/script the user just typed in, even if that differs from previous turns — automatically detect and match it, the way a native bilingual speaker would, instead of forcing a fixed language.
Keep the tone warm, clear, and conversational. Use short paragraphs or bullet points if helpful. Keep greetings and small talk replies short and natural — don't over-explain.

If the user is just greeting you (e.g. "hi", "hello", "hey") or making small talk — including casual phrases in other languages like "k xa", "sanchai xau", "kasto cha" — respond naturally and warmly without forcing in unrelated context.

If the user asks a substantive question, answer using the retrieved context below. If the context does not contain the answer, or if the retrieved context is clearly unrelated to the question, say so honestly and offer to help directly instead of forcing the irrelevant context into your answer.

{history_block}Retrieved context:
{context}

Current question:
{question}

Answer:"""

    # ---------------- 4. GENERATE ----------------

    def generate_answer(self, prompt: str) -> str:
        import groq

        try:
            response = self.groq.chat.completions.create(
                model=GROQ_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except groq.RateLimitError:
            return (
                "⚠️ I've hit Groq's rate limit for the moment. Please wait a few "
                "seconds and try again — Groq's free tier resets quickly "
                "(per-minute limits, not daily)."
            )
        except groq.AuthenticationError:
            return "⚠️ Groq rejected the API key — double check GROQ_API_KEY in your .env file."
        except groq.APIError as e:
            return f"⚠️ Something went wrong talking to Groq: {e}"
        except Exception as e:
            return f"⚠️ Unexpected error generating a response: {e}"

    # ---------------- CONVERSATION SUMMARIZATION ----------------

    def summarize_conversation(self, history: list, previous_summary: str = None) -> str:
        """Condenses a chat history (optionally folded on top of an existing
        summary) into a short, information-dense recap: topics discussed,
        decisions/answers given, and anything unresolved. Used to (a) show
        the user a quick recap when they return to an old chat, and (b) keep
        long-chat prompts small by feeding this instead of the full history.
        """
        if not history:
            return previous_summary or ""

        turns = []
        for h in history:
            role = "User" if h["role"] == "user" else "Assistant"
            turns.append(f"{role}: {h['content']}")
        transcript = "\n".join(turns)

        prior_block = f"Existing summary of earlier parts of this chat:\n{previous_summary}\n\n" if previous_summary else ""

        prompt = (
            "Summarize the following chat conversation in 3-5 concise bullet points. "
            "Focus on: what topics/questions the user asked about, what key answers or information "
            "were given, and anything left unresolved. Write it as a quick recap for the user "
            "returning to this chat later, in their own conversation's language if it's not English. "
            "Do not include any preamble like 'Here is a summary' — just the bullets.\n\n"
            f"{prior_block}Conversation to fold in:\n{transcript}"
        )
        return self.generate_answer(prompt)

    # ---------------- full pipeline ----------------

    def answer(self, question: str, history: list, lang_name: str, user_name: str = None):
        """Runs the full pipeline end-to-end. Returns dict with all metadata."""

        # 0. MODERATE — block unsafe content before anything else runs.
        blocked, reason, mod_message = self.moderate(question)
        if blocked:
            return {
                "answer": mod_message,
                "source": "Blocked",
                "score": 1.0,
                "blocked": True,
                "image_url": None,
                "fetched_url": None,
            }

        # Image request short-circuit.
        image_request = self.maybe_fetch_image(question)
        if image_request:
            return {
                "answer": f"Here's an image for **{image_request['query']}**:",
                "source": "Image Search",
                "score": 1.0,
                "blocked": False,
                "image_url": image_request["url"],
                "fetched_url": None,
            }

        # URL fetch + summarize short-circuit.
        url_result = self.maybe_fetch_url(question)
        if url_result:
            if url_result.get("error"):
                answer_text = f"⚠️ {url_result['error']}"
            else:
                answer_text = f"**{url_result['title']}**\n\n{url_result['summary']}"
            return {
                "answer": answer_text,
                "source": "Web Fetch",
                "score": 1.0,
                "blocked": False,
                "image_url": None,
                "fetched_url": url_result["url"],
            }

        is_greeting = _looks_like_greeting(question)

        if is_greeting:
            context, source, score = "(greeting — no retrieval needed)", "Conversational", 1.0
        else:
            context, source, score = self.retrieve(question)

        prompt = self.build_prompt(question, context, history, lang_name, user_name)
        answer_text = self.generate_answer(prompt)

        return {
            "answer": answer_text,
            "source": source,
            "score": score,
            "blocked": False,
            "image_url": None,
            "fetched_url": None,
        }


# =============================================================================
# MODERATION
# =============================================================================

# Heuristic, keyword-based moderation. This is intentionally simple and
# transparent (no external classifier dependency) — good enough to catch
# clearly unsafe requests in a learning/internal project, but NOT a
# substitute for a real trust & safety pipeline in a production system.
_HARMFUL_PATTERNS = [
    r"\bhow (?:do|can) i (?:make|build|create) (?:a )?(?:bomb|explosive|weapon)\b",
    r"\b(?:make|build|synthesize) .*(?:bomb|explosive|nerve agent|chemical weapon|bioweapon)\b",
    r"\bhow to (?:kill|murder|hurt|harm) (?:someone|somebody|a person|my\b)",
    r"\bhow (?:do|can) i (?:hack|break into) .* (?:account|system|network)\b",
    r"\bchild (?:sexual|porn|abuse)\b",
    r"\bhow to (?:make|cook) (?:meth|crystal meth|fentanyl|heroin)\b",
    r"\bhow to (?:get away with|commit) .*(?:murder|crime|fraud)\b",
]
_SELF_HARM_PATTERNS = [
    r"\bkill myself\b",
    r"\bwant to die\b",
    r"\bend my life\b",
    r"\bsuicid",
    r"\bself[- ]harm\b",
    r"\bhurt myself\b",
]

_REFUSAL_MESSAGE = (
    "I can't help with that request — it could enable serious harm, so I'm not going to "
    "provide details on it. If there's something else I can help you with, including a "
    "safer way to approach whatever you're trying to do, I'm glad to help with that instead."
)

_SELF_HARM_MESSAGE = (
    "I'm really sorry you're going through this — it sounds like a genuinely hard moment, "
    "and I want you to be safe. I'm not the right support for this, but please consider "
    "reaching out to a crisis line or someone you trust right now. In the US you can call or "
    "text **988** (Suicide & Crisis Lifeline); outside the US, https://findahelpline.com lists "
    "local options. If you're in immediate danger, please contact local emergency services."
)


def moderate_text(text: str):
    """Returns (blocked: bool, reason: str | None, message: str | None)."""
    if not text:
        return False, None, None

    lowered = text.lower()

    for pattern in _SELF_HARM_PATTERNS:
        if re.search(pattern, lowered):
            return True, "self_harm", _SELF_HARM_MESSAGE

    for pattern in _HARMFUL_PATTERNS:
        if re.search(pattern, lowered):
            return True, "harmful_content", _REFUSAL_MESSAGE

    return False, None, None


# =============================================================================
# IMAGE FETCHING
# =============================================================================

_IMAGE_REQUEST_PATTERNS = [
    r"(?:show|send|give|find)\s+(?:me\s+)?(?:an?\s+)?(?:image|picture|photo)s?\s+of\s+(.+)",
    r"(?:image|picture|photo)\s*:\s*(.+)",
    r"what does\s+(.+?)\s+look like",
]


def detect_image_request(text: str):
    """Returns the image search query if the message is asking for an image, else None."""
    if not text:
        return None
    cleaned = text.strip().rstrip("?.! ")
    for pattern in _IMAGE_REQUEST_PATTERNS:
        m = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def fetch_image_url(query: str) -> str:
    """Resolves a search query to a real, directly-loadable image URL.

    Uses Unsplash's keyless "Source" redirect endpoint, which returns a real
    photo matching the query without requiring an API key. Falls back to a
    placeholder image service if the request fails for any reason.
    """
    safe_query = requests.utils.quote(query)
    primary_url = f"https://source.unsplash.com/featured/800x600/?{safe_query}"
    try:
        resp = requests.get(primary_url, timeout=6, allow_redirects=True)
        if resp.status_code == 200 and resp.url:
            return resp.url
    except requests.RequestException:
        pass

    # Fallback: a simple placeholder so the UI never breaks even if Unsplash
    # is unreachable (e.g. no internet access in the deployment environment).
    return f"https://placehold.co/800x600?text={safe_query.replace('%20', '+')}"


# =============================================================================
# URL FETCHING (with SSRF protection) + INPUT SANITIZATION
# =============================================================================

_URL_REGEX = re.compile(r"https?://[^\s<>\"']+")

# Internal/cloud-metadata hosts that must never be reachable from a fetched
# URL, even if they resolve through DNS rather than appearing as a literal IP.
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal"}


def extract_url(text: str):
    """Returns the first http(s) URL found in the message, or None."""
    if not text:
        return None
    m = _URL_REGEX.search(text)
    return m.group(0).rstrip(").,!?\"'") if m else None


def is_url_safe(url: str):
    """Blocks SSRF vectors: only public http(s) hosts are allowed — no
    localhost, no link-local/private/reserved IP ranges, no cloud metadata
    endpoints, and no non-http(s) schemes. Returns (is_safe: bool, reason: str|None).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "malformed URL"

    if parsed.scheme not in ("http", "https"):
        return False, "only http/https URLs are allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "no hostname found"

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return False, "internal hostnames are blocked"

    try:
        resolved_ips = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False, "hostname could not be resolved"

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, "URL resolves to a private/internal address"

    return True, None


def fetch_url_content(url: str, max_bytes: int = 1_500_0000000):
    """Fetches a URL and extracts readable title + body text. Caps response
    size to avoid resource-exhaustion from huge or malicious responses."""
    headers = {"User-Agent": "HybridAIChatbot/1.0 (+https://lict.edu.np)"}
    resp = requests.get(url, headers=headers, timeout=1, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type and "text" not in content_type:
        raise ValueError("URL does not point to readable text/HTML content")

    raw = b""
    for chunk in resp.iter_content(chunk_size=9000):
        raw += chunk
        if len(raw) > max_bytes:
            break

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = " ".join(soup.get_text(separator=" ").split())

    return {"title": title, "text": text}


def sanitize_user_input(text: str) -> str:
    """Strips HTML/script content from user input before it's stored or
    rendered, to prevent stored-XSS via the chat history (messages are
    rendered with unsafe_allow_html=True for styling purposes, so raw user
    HTML must never reach that path unescaped)."""
    if not text:
        return text
    # Remove any HTML tags entirely rather than escaping, since the chat
    # bubble HTML wrapper itself depends on unsafe_allow_html.
    no_tags = re.sub(r"<[^>]*>", "", text)
    # Strip null bytes and control characters that have no place in chat text.
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", no_tags)
    return cleaned.strip()


# =============================================================================
# LANGUAGE / TONE DETECTION
# =============================================================================

_GREETING_WORDS = {
    "hi", "hello", "hey", "yo", "namaste", "hola", "bonjour",
    "good morning", "good afternoon", "good evening", "sup", "hii", "heyy",
}

_SMALL_TALK_PHRASES = {
    "k xa", "k cha", "k chha", "kasto xa", "kasto cha", "kasto chha",
    "sanchai", "sanchai xau", "sanchai cha", "sanchai chau",
    "k xa sanchai xau", "k cha sanchai chau", "tapai kasto hunuhuncha",
    "kti bje", "k garira", "k garaira", "khana khayou", "khana khayo",
    "thik xu", "thik cha", "malai thaha xaina", "ramro cha",
}

_ROMANIZED_NEPALI_HINTS = {
    "xa", "xau", "xan", "xayo", "xaina", "cha", "chau", "chan", "chha",
    "vanda", "vanera", "vannu", "garnu", "garera", "garira", "garaira",
    "malai", "timilai", "tapailai", "hamilai", "uslai", "yo", "tyo",
    "k", "ke", "kasto", "kati", "kahile", "kaha", "kasari", "kina",
    "ho", "haina", "thik", "sanchai", "namaste", "dhanyabad", "maaf",
    "ramro", "naramro", "khana", "khayo", "khayou", "ghar", "kaam",
    "didi", "bhai", "dai", "bahini", "saathi", "sathi", "ramailo",
}

_DISCOURAGED_WORDS = {
    "stressed", "tired", "exhausted", "overwhelmed", "sad", "depressed",
    "anxious", "worried", "burnt out", "burned out", "hopeless", "lost",
    "struggling", "down", "discouraged", "demotivated", "drained",
}
_FRUSTRATED_WORDS = {
    "frustrated", "annoyed", "angry", "furious", "fed up", "irritated", "mad",
}
_POSITIVE_WORDS = {
    "excited", "happy", "great news", "thrilled", "awesome", "amazing", "proud",
}


def detect_tone(text: str) -> str:
    """Very lightweight keyword-based sentiment detection.

    Returns one of: "discouraged", "frustrated", "positive", "neutral".
    """
    lowered = (text or "").lower()
    if any(w in lowered for w in _DISCOURAGED_WORDS):
        return "discouraged"
    if any(w in lowered for w in _FRUSTRATED_WORDS):
        return "frustrated"
    if any(w in lowered for w in _POSITIVE_WORDS):
        return "positive"
    return "neutral"


def detect_input_language(text: str) -> str:
    if not text:
        return ""

    if any("\u0900" <= ch <= "\u097F" for ch in text):
        return "nepali_devanagari"

    cleaned = text.strip().lower().strip("!.,?")
    words = cleaned.split()
    if not words:
        return ""

    hint_hits = sum(1 for w in words if w.strip("!.,?") in _ROMANIZED_NEPALI_HINTS)

    normalized = " ".join(words)
    if any(phrase in normalized for phrase in _SMALL_TALK_PHRASES):
        return "nepali_romanized"
    if len(words) <= 4 and hint_hits >= 1:
        return "nepali_romanized"
    if hint_hits >= 2:
        return "nepali_romanized"

    return ""


def _looks_like_greeting(text: str) -> bool:
    cleaned = text.strip().lower().strip("!.,? ")
    if cleaned in _GREETING_WORDS or cleaned in _SMALL_TALK_PHRASES:
        return True

    normalized = " ".join(cleaned.split())
    for phrase in _SMALL_TALK_PHRASES:
        if phrase in normalized:
            return True

    first_word = cleaned.split(" ")[0] if cleaned else ""
    return len(cleaned.split()) <= 3 and first_word in _GREETING_WORDS


# =============================================================================
# Runnable CLI entry point
# =============================================================================

def main():
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")

    if not groq_key:
        print("ERROR: GROQ_API_KEY not found. Set it in a .env file or your environment.")
        sys.exit(1)
    if not tavily_key:
        print("WARNING: TAVILY_API_KEY not set — web search fallback will fail if triggered.")

    print("Loading embedder and building index (this can take a few seconds the first time)...")
    pipeline = RagPipeline(
        groq_key=groq_key,
        tavily_key=tavily_key,
        data_path="data.json",
    )
    print(f"Ready. Using Groq model: {GROQ_MODEL_NAME}")
    print("Try: 'show me an image of the office', or type in Romanized Nepali like 'k xa sanchai xau'.")
    print("Type your question and press Enter. Type 'exit' or 'quit' to stop.\n")

    history = []
    lang_name = "English"
    user_name = None

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        result = pipeline.answer(question, history, lang_name, user_name)

        print(f"\nAssistant ({result['source']}, score={result['score']:.2f}):")
        print(result["answer"])
        if result.get("image_url"):
            print(f"[image] {result['image_url']}")
        print()

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result["answer"]})


if __name__ == "__main__":
    main()