"""Baut aus dem Briefing einen GitHub-Eintrag, den GitHub als Mail verschickt."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from .config import load_config
from .textutil import safe_url

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]
MAX_CHARS = 60000
_MARKUP = re.compile(r"([\\`*_{}\[\]<>|~])")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def escape(text: str) -> str:
    """Feed-Texte dürfen keine Formatierung, Erwähnungen oder Verweise auslösen."""
    return _MARKUP.sub(r"\\\1", text).replace("@", "@\u200b").replace("#", "#\u200b")


def german_date(day: str) -> str:
    value = date.fromisoformat(day)
    return f"{WEEKDAYS[value.weekday()]}, {value.day}. {MONTHS[value.month - 1]} {value.year}"


def _links(story: dict) -> str:
    parts = []
    for link in story.get("links", []):
        url = safe_url(link.get("url"))
        if url:
            url = url.replace("(", "%28").replace(")", "%29")
            parts.append(f"[{escape(link['source'])}]({url})")
    return " · ".join(parts)


def _story(story: dict, prefix: str, indent: str) -> str:
    lines = [f"{prefix}**{escape(story['title'])}**  "]
    if story.get("summary"):
        lines.append(f"{indent}{escape(' '.join(story['summary']))}  ")
    note = " (nur eine Quelle)" if story.get("single_source") else ""
    lines.append(f"{indent}{_links(story)}{note}")
    return "\n".join(lines)


def build_body(payload: dict, owner: str, site_url: str, topics: list[str] | None = None,
               max_chars: int = MAX_CHARS) -> str:
    wanted = set(topics or [t["id"] for t in payload["topics"]])
    stories = sorted((s for s in payload["stories"] if s["topic"] in wanted), key=lambda s: s["rank"])
    top_count = int(payload["top_count"])
    top, rest = stories[:top_count], stories[top_count:]
    greeting = f"Guten Morgen @{owner}!" if _LOGIN.match(owner) else "Guten Morgen!"
    head = [
        greeting,
        "",
        f"**{german_date(payload['date'])}** · {len(stories)} Meldungen · [Auf der Seite lesen und ausklappen]({site_url})",
        "",
        "Fremdsprachige Texte sind maschinell übersetzt. Maßgeblich sind die verlinkten Originale.",
        "",
        "## Das Wichtigste",
        "",
    ]
    blocks = ["\n".join(head)]
    blocks.extend(_story(story, f"{number}. ", "   ") for number, story in enumerate(top, start=1))
    for topic in payload["topics"]:
        items = [s for s in rest if s["topic"] == topic["id"]]
        if items:
            blocks.append(f"## {escape(topic['label'])}")
            blocks.extend(_story(story, "- ", "  ") for story in items)
    body = ""
    ending = f"\n\n[Alle weiteren Meldungen auf der Seite]({site_url})"
    for block in blocks:
        if len(body) + len(block) + len(ending) + 2 > max_chars:
            return body + ending
        body += block + "\n\n"
    return body.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data", default="site/data")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--title-file", default="title.txt")
    parser.add_argument("--body-file", default="body.md")
    args = parser.parse_args()
    config = load_config(args.config)
    data = Path(args.data)
    day = json.loads((data / "index.json").read_text(encoding="utf-8"))["dates"][0]
    payload = json.loads((data / f"{day}.json").read_text(encoding="utf-8"))
    site_url = f"https://{args.owner.lower()}.github.io/{args.repo}/"
    topics = (config.get("mail") or {}).get("topics") or None
    Path(args.title_file).write_text(f"Morgenbriefing: {german_date(day)}", encoding="utf-8")
    Path(args.body_file).write_text(build_body(payload, args.owner, site_url, topics), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
