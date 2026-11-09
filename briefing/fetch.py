"""Ruft RSS-Feeds ab. Beachtet robots.txt; ein Ausfall stoppt den Lauf nicht."""
from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from urllib import robotparser
from urllib.parse import urlsplit

import feedparser
import requests

from .models import Article, Source, SourceStatus
from .textutil import clean_text, safe_url, strip_kicker


class _Robots:
    """Zwischenspeicher für robots.txt je Host."""

    def __init__(self, user_agent: str, timeout: float) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.cache: dict[str, robotparser.RobotFileParser | str] = {}
        self.lock = Lock()

    def _load(self, base: str) -> robotparser.RobotFileParser | str:
        parser = robotparser.RobotFileParser()
        try:
            response = requests.get(
                f"{base}/robots.txt",
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return "unreachable"
        if response.status_code >= 500:
            return "unreachable"
        if response.status_code >= 400:
            parser.parse([])
        else:
            parser.parse(response.text.splitlines())
        return parser

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self.lock:
            entry = self.cache.get(base)
        if entry is None:
            entry = self._load(base)
            with self.lock:
                self.cache[base] = entry
        if entry == "unreachable":
            return False
        return entry.can_fetch(self.user_agent, url)


def _entry_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def parse_feed(source: Source, content: bytes, max_items: int, max_future: timedelta = timedelta(hours=2),
               now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(timezone.utc)
    parsed = feedparser.parse(content)
    articles: list[Article] = []
    for entry in parsed.entries:
        title = strip_kicker(clean_text(entry.get("title")))
        url = safe_url(entry.get("link"))
        published = _entry_date(entry)
        if not title or not url or not published or published > now + max_future:
            continue
        categories = [clean_text(tag.get("term")) for tag in entry.get("tags", []) if tag.get("term")]
        description = clean_text(entry.get("summary"))
        articles.append(Article(source, title, description, url, published, categories))
    articles.sort(key=lambda a: a.published, reverse=True)
    return articles[:max_items]


def _fetch_one(source: Source, settings: dict, robots: _Robots, now: datetime) -> tuple[list[Article], SourceStatus]:
    limit = int(settings["max_feed_bytes"])
    try:
        if not robots.allowed(source.url):
            return [], SourceStatus(source, False, reason="durch robots.txt nicht erlaubt oder nicht prüfbar")
        with requests.get(
            source.url,
            headers={"User-Agent": settings["user_agent"], "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
            timeout=settings["request_timeout_seconds"],
            stream=True,
        ) as response:
            if response.status_code != 200:
                return [], SourceStatus(source, False, reason=f"HTTP {response.status_code}")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > limit:
                    return [], SourceStatus(source, False, reason="Feed zu groß")
    except requests.RequestException as error:
        return [], SourceStatus(source, False, reason=f"nicht erreichbar ({type(error).__name__})")

    articles = parse_feed(source, bytes(content), int(settings["max_items_per_source"]), now=now)
    if not articles:
        return [], SourceStatus(source, False, reason="keine lesbaren Einträge")
    newest = articles[0].published
    if now - newest > timedelta(hours=float(settings["stale_after_hours"])):
        return [], SourceStatus(source, False, len(articles), "veraltet", newest)
    return articles, SourceStatus(source, True, len(articles), "", newest)


def fetch_all(sources: list[Source], settings: dict, now: datetime | None = None) -> tuple[list[Article], list[SourceStatus]]:
    now = now or datetime.now(timezone.utc)
    robots = _Robots(settings["user_agent"], float(settings["request_timeout_seconds"]))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda source: _fetch_one(source, settings, robots, now), sources))
    articles = [article for found, _ in results for article in found]
    return articles, [status for _, status in results]
