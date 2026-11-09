"""Text-Vektoren, lokal berechnet. Ohne Schlüssel und ohne Online-Dienst."""
from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    threshold: float
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedder:
    """Mehrsprachiges Modell; erkennt dasselbe Ereignis auch über Sprachgrenzen."""

    def __init__(self, model_name: str, threshold: float) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name)
        self.threshold = threshold
        self.name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384))
        vectors = np.array(list(self.model.embed(texts, batch_size=32)), dtype=float)
        return _normalize(vectors)


class HashingEmbedder:
    """Notlösung ohne Modell. Funktioniert nur innerhalb einer Sprache."""

    def __init__(self, threshold: float) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self.vectorizer = HashingVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), n_features=2**16, alternate_sign=False, norm="l2"
        )
        self.threshold = threshold
        self.name = "Zeichen-Hashing (Notlösung)"

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 2**16))
        return _normalize(self.vectorizer.transform(texts).toarray())


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def build_embedder(settings: dict) -> tuple[Embedder, str | None]:
    """Gibt den Embedder und, falls nötig, eine Warnung für die Seite zurück."""
    try:
        return FastEmbedder(settings["embedding_model"], float(settings["similarity_threshold"])), None
    except Exception as error:  # Modell nicht ladbar: Briefing trotzdem erzeugen
        log.warning("Sprachmodell nicht verfügbar: %s", error)
        warning = "Die Gruppierung über Sprachgrenzen war heute eingeschränkt."
        return HashingEmbedder(float(settings["fallback_similarity_threshold"])), warning
