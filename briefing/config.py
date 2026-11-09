"""Lädt und prüft config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Source

ALLOWED_REGIONS = {
    "deutschland", "europa", "nordamerika", "lateinamerika",
    "afrika", "nahost", "asien", "ozeanien",
}


class ConfigError(ValueError):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    validate(config)
    return config


def validate(config: dict[str, Any]) -> None:
    topic_ids = [topic["id"] for topic in config["topics"]]
    if len(topic_ids) != len(set(topic_ids)):
        raise ConfigError("Themen-IDs müssen eindeutig sein.")
    if "weltpolitik" not in topic_ids:
        raise ConfigError("Das Thema 'weltpolitik' wird als Auffangthema gebraucht.")
    seen: set[str] = set()
    for raw in config["sources"]:
        source_id = raw.get("id", "?")
        if source_id in seen:
            raise ConfigError(f"Quelle doppelt: {source_id}")
        seen.add(source_id)
        if raw.get("region") not in ALLOWED_REGIONS:
            raise ConfigError(f"Quelle {source_id}: unbekannte Region {raw.get('region')!r}")
        lock = raw.get("topic_lock")
        if lock and lock not in topic_ids:
            raise ConfigError(f"Quelle {source_id}: unbekanntes Thema {lock!r}")
        if not str(raw.get("url", "")).startswith(("https://", "http://")):
            raise ConfigError(f"Quelle {source_id}: ungültige Adresse")


def build_sources(config: dict[str, Any], include_disabled: bool = False) -> list[Source]:
    sources = [Source(**raw) for raw in config["sources"]]
    if include_disabled:
        return sources
    return [source for source in sources if source.enabled]


def load_glossary(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return {"keep": data.get("keep") or [], "replace": data.get("replace") or {}}
