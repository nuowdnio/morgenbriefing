"""Kommandozeile: python -m briefing.main"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import build_sources, load_config, load_glossary
from .embed import build_embedder
from .pipeline import BriefingError, run_pipeline
from .translate import GlossaryTranslator, TranslationError, build_translator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Erstellt das tägliche News-Briefing.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--glossary", default="glossary.yaml")
    parser.add_argument("--output", default="site/data")
    parser.add_argument("--skip-if-today", action="store_true", help="Nichts tun, wenn heute schon ein Briefing existiert.")
    parser.add_argument("--not-before", help="Vor dieser Uhrzeit (HH:MM, Ortszeit) nichts tun.")
    return parser.parse_args(argv)


def report_built(built: bool) -> None:
    """Teilt GitHub mit, ob ein neues Briefing entstanden ist."""
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"built={'true' if built else 'false'}\n")


def is_too_early(now: datetime, not_before: str | None) -> bool:
    return bool(not_before) and now.time() < time.fromisoformat(not_before)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)
    config = load_config(args.config)
    settings = config["settings"]
    output = Path(args.output)
    local_now = datetime.now(timezone.utc).astimezone(ZoneInfo(settings["timezone"]))
    today = local_now.date()
    if is_too_early(local_now, args.not_before):
        logging.info("Noch zu früh, der nächste geplante Lauf übernimmt.")
        report_built(False)
        return 0
    if args.skip_if_today and (output / f"{today.isoformat()}.json").exists():
        logging.info("Für heute existiert bereits ein Briefing.")
        report_built(False)
        return 0

    translator = GlossaryTranslator(build_translator(settings["translator"]), load_glossary(args.glossary))
    embedder, warning = build_embedder(settings)
    try:
        payload = run_pipeline(
            config, build_sources(config), translator, embedder, output,
            warnings=[warning] if warning else [],
        )
    except (BriefingError, TranslationError) as error:
        logging.error("Lauf abgebrochen, das letzte Briefing bleibt online: %s", error)
        return 1
    logging.info("Briefing für %s mit %d Meldungen geschrieben.", payload["date"], len(payload["stories"]))
    report_built(True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
