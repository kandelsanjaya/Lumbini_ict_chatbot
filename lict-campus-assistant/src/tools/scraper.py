"""
scraper.py
Fetches real page content from https://lict.edu.np/ and folds it into
data.json's knowledge base, then rebuilds the searchable chunk index
(search_index.py) so the chatbot can retrieve grounded answers instead of
guessing.

Run standalone whenever you want fresh data:
    python scraper.py

Safe by design:
    - Only ever fetches lict.edu.np (allowlisted host) — never follows
      offsite links.
    - Strips scripts/styles before extracting text.
    - Caps total pages fetched so a bad sitemap can't turn this into a
      runaway crawl.
    - Every fetch has a timeout; failures are logged and skipped, never
      fatal to the whole run.
"""

import re
import time
import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.tools import utils
from src.tools import search_index

ALLOWED_HOST = "lict.edu.np"
SEED_URLS = [
    "https://lict.edu.np/",
    "https://lict.edu.np/bsc-csit/",
    "https://lict.edu.np/bca/",
    "https://lict.edu.np/bim/",
    "https://lict.edu.np/bhm/",
]
MAX_PAGES = 25
REQUEST_TIMEOUT = 12
HEADERS = {"User-Agent": "LICTCampusAssistantBot/1.0 (+https://lict.edu.np)"}


def _same_host(url: str) -> bool:
    try:
        return urlparse(url).netloc.replace("www.", "") == ALLOWED_HOST
    except ValueError:
        return False


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text


def _fetch(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"  ⚠️  skipped {url}: {e}")
        return None


def scrape_site(seed_urls=None, max_pages=MAX_PAGES):
    """Crawls lict.edu.np starting from seed_urls (same-host only, capped at
    max_pages). Returns a list of {url, title, text} dicts."""
    seed_urls = seed_urls or SEED_URLS
    to_visit = list(dict.fromkeys(seed_urls))  # de-duped, order preserved
    visited = set()
    pages = []

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)
        if url in visited or not _same_host(url):
            continue
        visited.add(url)

        print(f"Fetching {url} ...")
        html = _fetch(url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        text = _clean_text(soup)
        if text:
            pages.append({"url": url, "title": title, "text": text[:8000]})

        # Discover more same-host links from this page (breadth-first, capped).
        for a in soup.find_all("a", href=True):
            link = urljoin(url, a["href"]).split("#")[0]
            if _same_host(link) and link not in visited and link not in to_visit:
                to_visit.append(link)

        time.sleep(0.4)  # be polite

    return pages


def update_knowledge_base_from_scrape(pages: list):
    """Merges freshly scraped pages into data.json's knowledge_base under
    'scraped_pages', then rebuilds the chunk search index."""
    data = utils.load_data()
    kb = data.setdefault("knowledge_base", {})
    kb["scraped_pages"] = pages
    kb["last_scraped"] = datetime.datetime.now().isoformat()
    utils.save_data(data)
    print(f"Saved {len(pages)} scraped pages into data.json.")

    chunks = search_index.build_index()
    print(f"Rebuilt search index: {len(chunks)} chunks.")


def run():
    print(f"Scraping {ALLOWED_HOST} (max {MAX_PAGES} pages)...")
    pages = scrape_site()
    update_knowledge_base_from_scrape(pages)
    print("Done.")


if __name__ == "__main__":
    run()
