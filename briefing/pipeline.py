"""Der Ablauf eines Briefings, von den Feeds bis zur Ausgabe."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .cluster import cluster_articles
from .embed import Embedder
from .fetch import fetch_all
from .filters import apply_exclusions, deduplicate, within_window
from .models import Article, Source, SourceStatus, Story
from .output import status_to_dict, story_to_dict, write_briefing
from .rank import score_story, select_stories
from .summarize import detail_sentences, pick_headline, select_sentences
from .textutil import normalize_title, safe_url
from .topics import TopicClassifier
from .translate import TranslationError, Translator

log = logging.getLogger(__name__)


class BriefingError(RuntimeError):
    """Der Lauf bricht ab; das letzte Briefing bleibt online."""


def prepare_articles(articles: list[Article], settings: dict, exclude: dict, now: datetime) -> list[Article]:
    recent = within_window(articles, now, float(settings["lookback_hours"]))
    return deduplicate(apply_exclusions(recent, exclude))


def build_stories(articles: list[Article], config: dict, embedder: Embedder, now: datetime) -> list[Story]:
    settings, ranking = config["settings"], config["ranking"]
    vectors = embedder.encode([article.text[:600] for article in articles])
    stories = cluster_articles(articles, vectors, embedder.threshold)
    topic_vectors = embedder.encode([t["description"] for t in config["topics"]])
    classifier = TopicClassifier(config["topics"], topic_vectors)
    weights = {t["id"]: float(t.get("weight", 1.0)) for t in config["topics"]}
    for story in stories:
        story.topic = classifier.assign(story, vectors)
        story.score = score_story(story, now, ranking, weights[story.topic])
    return select_stories(
        stories,
        float(ranking["diversity_penalty"]),
        int(settings["max_stories_per_topic"]),
        int(settings["max_stories_total"]),
    )


def build_details(story: Story, headline: Article, shown: set[str], settings: dict, translator: Translator) -> list[dict]:
    """Inhalt zum Ausklappen: was die einzelnen Feeds über die Kurzfassung hinaus enthalten."""
    target = settings["target_language"]
    limit = int(settings.get("max_detail_chars", 700))
    details: list[dict] = []
    seen_urls: set[str] = set()
    for article in sorted(story.articles, key=lambda a: a.source.weight, reverse=True):
        url = safe_url(article.url)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        language = article.source.language
        extra = detail_sentences(article, shown, limit)
        same_title = normalize_title(article.title) == normalize_title(headline.title)
        if same_title and not extra:
            continue
        try:
            title = "" if same_title else translator.translate(article.title, language, target)
            text = [translator.translate(sentence, language, target) for sentence in extra]
        except Exception as error:
            log.warning("Zusatztext übersprungen (%s): %s", article.url, error)
            continue
        details.append({
            "source": article.source.name,
            "country": article.source.country,
            "url": url,
            "title": title,
            "text": text,
            "machine_translated": language != target,
        })
    return details


def localize(stories: list[Story], settings: dict, translator: Translator) -> list[Story]:
    """Übersetzt nur ausgewählte Meldungen; misslungene Meldungen entfallen."""
    target = settings["target_language"]
    finished: list[Story] = []
    for story in stories:
        headline = pick_headline(story, target)
        sentences, language = select_sentences(
            story, headline.title, target,
            int(settings["max_summary_sentences"]), int(settings["max_summary_chars"]),
        )
        translated = headline.source.language != target or (language is not None and language != target)
        try:
            story.title = translator.translate(headline.title, headline.source.language, target)
            story.summary = [translator.translate(s, language, target) for s in sentences]
        except Exception as error:
            log.warning("Übersetzung übersprungen (%s): %s", headline.url, error)
            continue
        story.machine_translated = translated
        story.details = build_details(story, headline, set(sentences), settings, translator)
        finished.append(story)
    return finished


def run_pipeline(config: dict, sources: list[Source], translator: Translator, embedder: Embedder,
                 output_dir: Path, now: datetime | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    settings = config["settings"]
    target = settings["target_language"]
    articles, statuses = fetch_all(sources, settings, now)
    ok_sources = sum(status.ok for status in statuses)
    log.info("Quellen erreichbar: %d von %d, Einträge: %d", ok_sources, len(statuses), len(articles))
    for status in statuses:
        if not status.ok:
            log.warning("Quelle ausgefallen: %s (%s)", status.source.name, status.reason)
    if ok_sources < int(settings["min_sources_ok"]):
        raise BriefingError(f"Nur {ok_sources} Quellen erreichbar, mindestens {settings['min_sources_ok']} nötig.")

    prepared = prepare_articles(articles, settings, config["exclude"], now)
    translator.prepare({a.source.language for a in prepared}, target)
    stories = build_stories(prepared, config, embedder, now)
    multi = sum(len(s.source_ids) > 1 for s in stories)
    log.info("Artikel im Zeitfenster: %d, ausgewählte Meldungen: %d, davon mehrere Quellen: %d", len(prepared), len(stories), multi)
    stories = localize(stories, settings, translator)
    if len(stories) < int(settings["min_stories"]):
        raise BriefingError(f"Nur {len(stories)} Meldungen erzeugt, mindestens {settings['min_stories']} nötig.")

    timezone_local = ZoneInfo(settings["timezone"])
    local_now = now.astimezone(timezone_local)
    payload = {
        "date": local_now.date().isoformat(),
        "generated_at": now.isoformat(),
        "window_hours": settings["lookback_hours"],
        "top_count": settings["top_count"],
        "translator": translator.name,
        "embedder": embedder.name,
        "warnings": warnings or [],
        "topics": [{"id": t["id"], "label": t["label"]} for t in config["topics"]],
        "stories": [story_to_dict(story, rank) for rank, story in enumerate(stories, start=1)],
        "sources": [status_to_dict(status) for status in statuses],
    }
    write_briefing(output_dir, local_now.date(), payload, int(settings["archive_days"]))
    return payload


__all__ = ["BriefingError", "TranslationError", "SourceStatus", "run_pipeline"]
