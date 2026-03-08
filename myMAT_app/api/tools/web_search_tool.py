from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def search_web_bullets(query: str, max_items: int = 5, timeout_s: int = 12) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        return {"bullets": [], "sources": []}

    url = f"https://duckduckgo.com/html/?q={quote_plus(clean_query)}"
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=timeout_s)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    bullets: list[str] = []
    sources: list[dict[str, Any]] = []

    result_nodes = soup.select("div.result")
    for node in result_nodes:
        title_node = node.select_one("a.result__a")
        snippet_node = node.select_one("a.result__snippet, div.result__snippet")
        if title_node is None:
            continue
        title = title_node.get_text(" ", strip=True)
        href = title_node.get("href", "")
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
        text = snippet or title
        if not text:
            continue
        bullets.append(text)
        sources.append(
            {
                "source": href or "web",
                "source_name": title or "web result",
                "doc_type": "web",
            }
        )
        if len(bullets) >= max_items:
            break

    if not bullets:
        bullets = ["No reliable web snippets were found for this query."]
        sources = []

    return {"bullets": bullets[:max_items], "sources": sources[:max_items]}
