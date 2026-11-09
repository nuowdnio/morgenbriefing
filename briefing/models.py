"""Gemeinsame Datenstrukturen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    id: str
    name: str
    url: str
    country: str
    region: str
    language: str
    ownership: str
    weight: float = 1.0
    enabled: bool = True
    topic_lock: str | None = None
    paywall: bool = False


@dataclass
class Article:
    source: Source
    title: str
    description: str
    url: str
    published: datetime
    categories: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"{self.title}. {self.description}".strip()


@dataclass
class SourceStatus:
    source: Source
    ok: bool
    items: int = 0
    reason: str = ""
    newest: datetime | None = None


@dataclass
class Story:
    articles: list[Article]
    embedding_indices: list[int] = field(default_factory=list)
    topic: str = ""
    score: float = 0.0
    title: str = ""
    summary: list[str] = field(default_factory=list)
    machine_translated: bool = False
    details: list[dict] = field(default_factory=list)

    @property
    def source_ids(self) -> set[str]:
        return {a.source.id for a in self.articles}

    @property
    def regions(self) -> set[str]:
        return {a.source.region for a in self.articles}

    @property
    def primary_region(self) -> str:
        counts: dict[str, float] = {}
        for article in self.articles:
            counts[article.source.region] = counts.get(article.source.region, 0) + article.source.weight
        return max(sorted(counts), key=counts.get)

    @property
    def newest(self) -> datetime:
        return max(a.published for a in self.articles)
