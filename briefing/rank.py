"""Regelbasierte Gewichtung und Auswahl mit regionaler Vielfalt."""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime

from .models import Story


def score_story(story: Story, now: datetime, ranking: dict, topic_weight: float) -> float:
    independent = len(story.source_ids)
    regions = len(story.regions)
    age_hours = max((now - story.newest).total_seconds() / 3600.0, 0.0)
    recency = 0.5 ** (age_hours / float(ranking["recency_half_life_hours"]))
    best_weight = max(article.source.weight for article in story.articles)
    base = (
        float(ranking["sources"]) * math.log2(1 + independent)
        + float(ranking["regions"]) * (regions - 1)
        + float(ranking["recency"]) * recency
        + float(ranking["source_weight"]) * best_weight
    )
    return base * topic_weight


def diverse_order(stories: list[Story], penalty: float) -> list[Story]:
    """Sortiert so, dass eine Region nicht alle vorderen Plätze belegt."""
    remaining = sorted(stories, key=lambda s: s.score, reverse=True)
    ordered: list[Story] = []
    used: Counter[str] = Counter()
    while remaining:
        best = max(remaining, key=lambda s: s.score / (1.0 + penalty * used[s.primary_region]))
        remaining.remove(best)
        ordered.append(best)
        used[best.primary_region] += 1
    return ordered


def select_stories(stories: list[Story], penalty: float, per_topic: int, total: int) -> list[Story]:
    selected: list[Story] = []
    counts: Counter[str] = Counter()
    for story in diverse_order(stories, penalty):
        if counts[story.topic] >= per_topic:
            continue
        selected.append(story)
        counts[story.topic] += 1
        if len(selected) >= total:
            break
    return selected
