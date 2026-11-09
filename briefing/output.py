"""Schreibt das Tagesbriefing als JSON und pflegt das Archiv."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .models import SourceStatus, Story
from .textutil import safe_url

DATE_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def story_to_dict(story: Story, rank: int) -> dict[str, Any]:
    seen: set[str] = set()
    links = []
    for article in sorted(story.articles, key=lambda a: a.source.weight, reverse=True):
        url = safe_url(article.url)
        if not url or url in seen:
            continue
        seen.add(url)
        links.append({
            "source": article.source.name,
            "country": article.source.country,
            "ownership": article.source.ownership,
            "url": url,
        })
    return {
        "rank": rank,
        "topic": story.topic,
        "title": story.title,
        "summary": story.summary,
        "machine_translated": story.machine_translated,
        "single_source": len(story.source_ids) == 1,
        "source_count": len(story.source_ids),
        "region_count": len(story.regions),
        "published": story.newest.isoformat(),
        "links": links,
        "details": story.details,
    }


def status_to_dict(status: SourceStatus) -> dict[str, Any]:
    return {
        "name": status.source.name,
        "country": status.source.country,
        "language": status.source.language,
        "ownership": status.source.ownership,
        "ok": status.ok,
        "items": status.items,
        "reason": status.reason,
    }


def _atomic_write(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    os.replace(temporary, path)


def write_briefing(data_dir: Path, day: date, payload: dict[str, Any], archive_days: int) -> list[str]:
    data_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(data_dir / f"{day.isoformat()}.json", payload)
    limit = day - timedelta(days=archive_days - 1)
    dates: list[str] = []
    for file in data_dir.iterdir():
        if not DATE_FILE.match(file.name):
            continue
        file_day = date.fromisoformat(file.stem)
        if file_day < limit:
            file.unlink()
        else:
            dates.append(file.stem)
    dates.sort(reverse=True)
    _atomic_write(data_dir / "index.json", {"dates": dates})
    return dates
