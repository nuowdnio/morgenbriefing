"""Prüft alle eingetragenen Feeds: python -m briefing.check_feeds --all"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .config import build_sources, load_config
from .fetch import fetch_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--all", action="store_true", help="Auch deaktivierte Quellen prüfen.")
    args = parser.parse_args()
    config = load_config(args.config)
    now = datetime.now(timezone.utc)
    _, statuses = fetch_all(build_sources(config, include_disabled=args.all), config["settings"], now)
    print("| Quelle | Aktiv | Ergebnis | Einträge | Neuester Eintrag |")
    print("|---|---|---|---|---|")
    for status in sorted(statuses, key=lambda s: (not s.ok, s.source.name)):
        result = "funktioniert" if status.ok else f"**Problem:** {status.reason}"
        newest = status.newest.strftime("%d.%m.%Y %H:%M UTC") if status.newest else "-"
        active = "ja" if status.source.enabled else "nein"
        print(f"| {status.source.name} | {active} | {result} | {status.items} | {newest} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
