"""Lädt und prüft config.yaml."""
from __future__ import annotations

import re
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
        if raw.get("enabled", True) and raw.get("paywall"):
            raise ConfigError(f"Quelle {source_id}: hat eine Bezahlschranke und darf nicht aktiv sein.")
        lock = raw.get("topic_lock")
        if lock and lock not in topic_ids:
            raise ConfigError(f"Quelle {source_id}: unbekanntes Thema {lock!r}")
        if not str(raw.get("url", "")).startswith(("https://", "http://")):
            raise ConfigError(f"Quelle {source_id}: ungültige Adresse")
    validate_markets(config.get("markets") or {})


def validate_markets(markets: dict[str, Any]) -> None:
    if not markets.get("enabled"):
        return
    symbols: set[str] = set()
    for entry in [e for g in markets.get("groups") or [] for e in g.get("items") or []] + (markets.get("companies") or []):
        if not entry.get("symbol") or not entry.get("name"):
            raise ConfigError("Börse: jeder Wert braucht symbol und name.")
        if entry["symbol"] in symbols:
            raise ConfigError(f"Börse: Kürzel doppelt: {entry['symbol']}")
        symbols.add(entry["symbol"])
        if entry.get("pattern"):
            try:
                re.compile(entry["pattern"])
            except re.error as error:
                raise ConfigError(f"Börse: ungültiges pattern bei {entry['name']}: {error}") from error
    trend_ids = [t.get("id") for t in markets.get("trends") or []]
    if len(trend_ids) != len(set(trend_ids)):
        raise ConfigError("Börse: Trend-IDs müssen eindeutig sein.")
    for trend in markets.get("trends") or []:
        unknown = [s for s in trend.get("symbols") or [] if s not in symbols]
        if unknown:
            raise ConfigError(f"Börse: Trend {trend.get('id')} nennt unbekannte Kürzel {unknown}")


def build_sources(config: dict[str, Any], include_disabled: bool = False) -> list[Source]:
    sources = [Source(**raw) for raw in config["sources"]]
    if include_disabled:
        return sources
    return [source for source in sources if source.enabled]


def load_glossary(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return {"keep": data.get("keep") or [], "replace": data.get("replace") or {}}
