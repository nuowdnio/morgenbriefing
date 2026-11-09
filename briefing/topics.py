"""Ordnet Ereignisse einem Thema zu."""
from __future__ import annotations

import re

import numpy as np

from .models import Article, Story

PATH_WEIGHT = 4.0
LOCK_WEIGHT = 6.0
KEYWORD_WEIGHT = 1.0
KEYWORD_CAP = 3
CATEGORY_WEIGHT = 2.0
EMBEDDING_WEIGHT = 2.0
FALLBACK_TOPIC = "weltpolitik"
MIN_SCORE = 1.0


def _compile(keyword: str) -> re.Pattern:
    # Abkürzungen wie EU oder KI nur in exakter Schreibweise
    flags = 0 if keyword.isupper() else re.IGNORECASE
    return re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", flags)


class TopicClassifier:
    def __init__(self, topics: list[dict], topic_vectors: np.ndarray) -> None:
        self.topics = topics
        self.topic_vectors = topic_vectors
        self.patterns = {t["id"]: [_compile(k) for k in t.get("keywords", [])] for t in topics}

    def _article_scores(self, article: Article, vector: np.ndarray | None) -> dict[str, float]:
        scores: dict[str, float] = {}
        similarity = vector @ self.topic_vectors.T if vector is not None and len(self.topic_vectors) else None
        categories = " ".join(article.categories).casefold()
        for index, topic in enumerate(self.topics):
            topic_id = topic["id"]
            score = 0.0
            if article.source.topic_lock == topic_id:
                score += LOCK_WEIGHT
            if any(hint in article.url for hint in topic.get("path_hints", [])):
                score += PATH_WEIGHT
            hits = sum(1 for pattern in self.patterns[topic_id] if pattern.search(article.text))
            score += min(hits, KEYWORD_CAP) * KEYWORD_WEIGHT
            if categories and (topic["label"].casefold() in categories or topic_id in categories):
                score += CATEGORY_WEIGHT
            if similarity is not None:
                score += max(float(similarity[index]), 0.0) * EMBEDDING_WEIGHT
            scores[topic_id] = score
        return scores

    def assign(self, story: Story, vectors: np.ndarray) -> str:
        totals = {topic["id"]: 0.0 for topic in self.topics}
        for article, index in zip(story.articles, story.embedding_indices):
            for topic_id, value in self._article_scores(article, vectors[index]).items():
                totals[topic_id] += value
        count = max(len(story.articles), 1)
        best = max(self.topics, key=lambda topic: totals[topic["id"]])["id"]
        return best if totals[best] / count >= MIN_SCORE else FALLBACK_TOPIC
