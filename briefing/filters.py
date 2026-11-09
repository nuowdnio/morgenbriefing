"""Zeitfenster, Ausschlüsse und Dubletten."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import Article
from .textutil import normalize_title, normalize_url


def within_window(articles: list[Article], now: datetime, hours: float) -> list[Article]:
    limit = now - timedelta(hours=hours)
    return [article for article in articles if article.published >= limit]


def apply_exclusions(articles: list[Article], exclude: dict) -> list[Article]:
    titles = [re.compile(pattern) for pattern in exclude.get("title_patterns", [])]
    urls = [re.compile(pattern) for pattern in exclude.get("url_patterns", [])]
    kept = []
    for article in articles:
        if any(pattern.search(article.title) for pattern in titles):
            continue
        if any(pattern.search(article.url) for pattern in urls):
            continue
        kept.append(article)
    return kept


def deduplicate(articles: list[Article]) -> list[Article]:
    """Behält je Adresse und je Quelle+Titel den neuesten Eintrag."""
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    unique: list[Article] = []
    for article in sorted(articles, key=lambda a: a.published, reverse=True):
        url_key = normalize_url(article.url)
        title_key = (article.source.id, normalize_title(article.title))
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(article)
    return unique
