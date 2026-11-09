"""Vergleicht Argos und Opus-MT an 20 aktuellen Meldungen und schreibt eine Tabelle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .config import build_sources, load_config
from .fetch import fetch_all
from .pipeline import prepare_articles
from .translate import ArgosTranslator, OpusTranslator


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    config = load_config(args.config)
    now = datetime.now(timezone.utc)
    articles, _ = fetch_all(build_sources(config), config["settings"], now)
    english = [a for a in prepare_articles(articles, config["settings"], config["exclude"], now) if a.source.language == "en"]
    sample = english[:: max(len(english) // args.count, 1)][: args.count]
    argos, opus = ArgosTranslator(), OpusTranslator()
    argos.prepare({"en"}, "de")
    opus.prepare({"en"}, "de")
    print("| Original | Argos Translate | Opus-MT |")
    print("|---|---|---|")
    for article in sample:
        print(f"| {_cell(article.title)} | {_cell(argos.translate(article.title, 'en', 'de'))} | {_cell(opus.translate(article.title, 'en', 'de'))} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
