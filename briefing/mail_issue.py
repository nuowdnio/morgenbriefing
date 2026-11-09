"""Baut aus dem Briefing einen GitHub-Eintrag, den GitHub als Mail verschickt."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from .config import load_config
from .numbers import change_de, number_de
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


def _price(item: dict) -> str:
    unit = item.get("unit") or ""
    value = number_de(item["price"], int(item.get("decimals", 2)))
    return f"{value} {escape(unit)}".strip()


def _absolute(item: dict) -> bool:
    return item.get("kind") == "yield"


def markets_block(markets: dict | None, site_url: str) -> str:
    """Börse & Märkte als Markdown: Kurstabelle, Unternehmen im Blick, Trends."""
    if not markets:
        return ""
    lines = ["## Börse & Märkte", ""]
    if not markets.get("available"):
        lines.append("Kursdaten waren heute nicht abrufbar.")
        return "\n".join(lines)
    if markets.get("summary"):
        lines += [escape(markets["summary"]), ""]
    for group in markets.get("groups", []):
        lines += [f"**{escape(group['label'])}**", "", "| Wert | Stand | Tag | 1 Monat | lfd. Jahr |", "|:--|--:|--:|--:|--:|"]
        for item in group["items"]:
            absolute = _absolute(item)
            lines.append(f"| {escape(item['name'])} | {_price(item)} | {change_de(item.get('change_1d'), absolute)} | "
                         f"{change_de(item.get('change_1m'), absolute)} | {change_de(item.get('change_ytd'), absolute)} |")
        lines.append("")
    if markets.get("watch"):
        lines += ["### Unternehmen im Blick", ""]
        for item in markets["watch"]:
            lines.append(f"- **{escape(item['name'])}** ({escape(item.get('sector', ''))}) · {_price(item)} · "
                         f"Tag {change_de(item.get('change_1d'))} · Monat {change_de(item.get('change_1m'))}  ")
            lines.append(f"  {escape('. '.join(item['reasons']))}.")
            for story in item.get("stories", []):
                url = safe_url(story.get("url"))
                if url:
                    url = url.replace("(", "%28").replace(")", "%29")
                    lines.append(f"  → [{escape(story['title'])}]({url})")
        lines.append("")
    if markets.get("trends"):
        lines += ["### Trends", ""]
        for trend in markets["trends"]:
            parts = [f"{trend['mentions']} Artikel heute"]
            if trend.get("direction"):
                parts[0] += f" ({trend['direction']}, Ø {number_de(trend['average'], 1)})"
            if trend.get("basket_1m") is not None:
                names = ", ".join(m["name"] for m in trend.get("members", []))
                parts.append(f"passende Werte im Monat {change_de(trend['basket_1m'])} ({escape(names)})")
            lines.append(f"- **{escape(trend['label'])}**: {escape('; '.join(parts))}")
        lines.append("")
    lines.append(f"_{escape(markets.get('source', ''))}. Keine Anlageberatung. Kurven und alle Werte [auf der Seite]({site_url})._")
    return "\n".join(lines)


def build_body(payload: dict, owner: str, site_url: str, topics: list[str] | None = None,
               max_chars: int = MAX_CHARS, markets: bool = True) -> str:
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
    tail = markets_block(payload.get("markets"), site_url) if markets else ""
    if tail and len(tail) > max_chars // 2:
        tail = ""
    body = ""
    ending = f"\n\n[Alle weiteren Meldungen auf der Seite]({site_url})"
    for block in blocks:
        if len(body) + len(block) + len(ending) + len(tail) + 4 > max_chars:
            body = body + ending.strip() + "\n\n"
            break
        body += block + "\n\n"
    if tail:
        body += tail + "\n"
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
    mail = config.get("mail") or {}
    topics = mail.get("topics") or None
    Path(args.title_file).write_text(f"Morgenbriefing: {german_date(day)}", encoding="utf-8")
    Path(args.body_file).write_text(build_body(payload, args.owner, site_url, topics, markets=bool(mail.get("markets", True))), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
