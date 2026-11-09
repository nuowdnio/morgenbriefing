"""Fasst Berichte über dasselbe Ereignis zusammen."""
from __future__ import annotations

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from .models import Article, Story


def cluster_articles(articles: list[Article], vectors: np.ndarray, threshold: float) -> list[Story]:
    if not articles:
        return []
    if len(articles) == 1:
        return [Story(articles=list(articles), embedding_indices=[0])]
    model = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1.0 - threshold,
    )
    labels = model.fit_predict(vectors)
    groups: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        groups.setdefault(int(label), []).append(index)
    return [
        Story(articles=[articles[i] for i in indices], embedding_indices=indices)
        for indices in groups.values()
    ]
