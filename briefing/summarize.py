"""Extraktive Zusammenfassung: Es werden nur vorhandene Feed-Sätze ausgewählt."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .models import Article, Story
from .textutil import jaccard, split_sentences, word_set

MIN_CHARS = 35
MAX_CHARS = 320
DUPLICATE_LIMIT = 0.55


@dataclass(frozen=True)
class Candidate:
    text: str
    language: str
    weight: float


def pick_headline(story: Story, target: str) -> Article:
    """Bevorzugt eine Originalzeile in der Zielsprache, dann die stärkste Quelle."""
    return max(
        story.articles,
        key=lambda a: (a.source.language == target, a.source.weight, a.published),
    )


def _candidates(story: Story) -> list[Candidate]:
    found: list[Candidate] = []
    for article in sorted(story.articles, key=lambda a: a.source.weight, reverse=True):
        for sentence in split_sentences(article.description):
            if MIN_CHARS <= len(sentence) <= MAX_CHARS and sentence[-1] in '.!?"“”…':
                found.append(Candidate(sentence, article.source.language, article.source.weight))
    return found


def _preferred_language(candidates: list[Candidate], target: str) -> str | None:
    """Eine Sprache je Meldung vermeidet Wiederholungen nach der Übersetzung."""
    if not candidates:
        return None
    if any(c.language == target for c in candidates):
        return target
    return Counter(c.language for c in candidates).most_common(1)[0][0]


def select_sentences(story: Story, headline: str, target: str, max_sentences: int, max_chars: int) -> tuple[list[str], str | None]:
    candidates = _candidates(story)
    language = _preferred_language(candidates, target)
    if language is None:
        return [], None
    candidates = [c for c in candidates if c.language == language]
    frequency: Counter[str] = Counter()
    for candidate in candidates:
        frequency.update(word_set(candidate.text))

    def value(candidate: Candidate) -> float:
        words = word_set(candidate.text)
        if not words:
            return 0.0
        coverage = sum(frequency[word] for word in words) / len(words)
        has_number = 0.3 if re.search(r"\d", candidate.text) else 0.0
        return coverage + has_number + 0.2 * candidate.weight

    chosen: list[str] = []
    used = 0
    for candidate in sorted(candidates, key=value, reverse=True):
        if len(chosen) >= max_sentences or used + len(candidate.text) > max_chars:
            continue
        if jaccard(candidate.text, headline) > DUPLICATE_LIMIT:
            continue
        if any(jaccard(candidate.text, other) > DUPLICATE_LIMIT for other in chosen):
            continue
        chosen.append(candidate.text)
        used += len(candidate.text)
    return chosen, language
