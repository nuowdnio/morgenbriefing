"""Börse und Märkte: Kurse, auffällige Unternehmen und Trendthemen.

Kurse kommen ohne Schlüssel von der frei abrufbaren Chart-Schnittstelle von Yahoo Finance.
Fällt sie aus, fehlt nur dieser Teil; das Nachrichten-Briefing entsteht trotzdem.
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests

from .models import Article, Story
from .numbers import change_de, number_de
from .output import DATE_FILE
from .textutil import safe_url

log = logging.getLogger(__name__)

SOURCE_NOTE = "Yahoo Finance, Kurse verzögert und ohne Gewähr"
CURRENCY_UNITS = {"EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CHF": "CHF", "HKD": "HK$", "DKK": "DKK", "TWD": "TWD"}
TRADING_DAYS = {"1w": 5, "1m": 21, "3m": 63}

Fetcher = Callable[[str], dict[str, Any]]


# ---------------------------------------------------------------- Abruf

def yahoo_fetcher(settings: dict, markets: dict) -> Fetcher:
    base = markets.get("provider_url", "https://query1.finance.yahoo.com/v8/finance/chart/")
    agent = markets.get("user_agent") or settings["user_agent"]
    timeout = float(settings["request_timeout_seconds"])

    def fetch(symbol: str) -> dict[str, Any]:
        url = f"{base}{quote(symbol, safe='')}?range=1y&interval=1d&includePrePost=false"
        for attempt in range(3):
            response = requests.get(url, headers={"User-Agent": agent, "Accept": "application/json"}, timeout=timeout)
            if response.status_code == 429 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("zu viele Anfragen")

    return fetch


def parse_chart(data: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[date, float]]]:
    """Liest Metadaten und Tagesschlusskurse aus einer Chart-Antwort."""
    result = data["chart"]["result"][0]
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0].get("close") or []
    series: list[tuple[date, float]] = []
    for stamp, close in zip(stamps, closes):
        if close is None or not math.isfinite(close) or close <= 0:
            continue
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).date()
        if series and series[-1][0] == day:
            series[-1] = (day, float(close))
        else:
            series.append((day, float(close)))
    if len(series) < 2:
        raise ValueError("zu wenige Kurse")
    return meta, series


# ---------------------------------------------------------------- Kennzahlen

def _change(series: list[tuple[date, float]], back: int, absolute: bool) -> float | None:
    if len(series) <= back:
        return None
    now, then = series[-1][1], series[-1 - back][1]
    return round(now - then if absolute else (now / then - 1) * 100, 2)


def _ytd(series: list[tuple[date, float]], absolute: bool) -> float | None:
    year = series[-1][0].year
    before = [close for day, close in series if day.year < year]
    base = before[-1] if before else None
    if base is None:
        return None
    now = series[-1][1]
    return round(now - base if absolute else (now / base - 1) * 100, 2)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _trend(closes: list[float]) -> str:
    price = closes[-1]
    if len(closes) >= 200:
        fast, slow = _mean(closes[-50:]), _mean(closes[-200:])
        if price > fast > slow:
            return "Aufwärtstrend"
        if price < fast < slow:
            return "Abwärtstrend"
        return "uneinheitlich"
    if len(closes) >= 50:
        fast = _mean(closes[-50:])
        return "Aufwärtstrend" if price > fast * 1.02 else "Abwärtstrend" if price < fast * 0.98 else "uneinheitlich"
    return ""


def _volatility(closes: list[float], days: int = 60) -> float | None:
    window = closes[-days - 1:]
    returns = [(b / a - 1) * 100 for a, b in zip(window, window[1:])]
    if len(returns) < 15:
        return None
    mean = _mean(returns)
    spread = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    return spread or None


def _decimals(price: float, configured: Any) -> int:
    if configured is not None:
        return int(configured)
    return 0 if price >= 10000 else 2 if price >= 1 else 4


def _spark(closes: list[float], points: int = 60) -> list[float]:
    tail = closes[-points:]
    return [float(f"{value:.5g}") for value in tail]


def quote_metrics(entry: dict, meta: dict, series: list[tuple[date, float]]) -> dict[str, Any]:
    closes = [close for _, close in series]
    absolute = entry.get("kind") == "yield"
    price = closes[-1]
    high, low = max(closes[-252:]), min(closes[-252:])
    volatility = _volatility(closes)
    change_1d = _change(series, 1, absolute)
    unusual = None
    if volatility and change_1d is not None and not absolute:
        unusual = round(abs(change_1d) / volatility, 1)
    return {
        "symbol": entry["symbol"],
        "name": entry["name"],
        "kind": "yield" if absolute else "price",
        "unit": entry.get("unit") or CURRENCY_UNITS.get(str(meta.get("currency", "")), str(meta.get("currency", ""))),
        "decimals": _decimals(price, entry.get("decimals")),
        "price": round(price, 6),
        "date": series[-1][0].isoformat(),
        "change_1d": change_1d,
        "change_1w": _change(series, TRADING_DAYS["1w"], absolute),
        "change_1m": _change(series, TRADING_DAYS["1m"], absolute),
        "change_ytd": _ytd(series, absolute),
        "change_1y": _change(series, len(series) - 1, absolute) if len(series) >= 240 else None,
        "from_high": round((price / high - 1) * 100, 1),
        "from_low": round((price / low - 1) * 100, 1),
        "new_high": len(closes) >= 120 and price >= high,
        "new_low": len(closes) >= 120 and price <= low,
        "trend": _trend(closes),
        "unusual": unusual,
        "spark": _spark(closes),
    }


def load_quotes(entries: list[dict], fetch: Fetcher, workers: int = 4) -> tuple[dict[str, dict], list[str]]:
    def one(entry: dict) -> tuple[dict, dict | None, str]:
        try:
            meta, series = parse_chart(fetch(entry["symbol"]))
            return entry, quote_metrics(entry, meta, series), ""
        except Exception as error:  # Ausfälle einzelner Werte sind erlaubt
            return entry, None, f"{type(error).__name__}"

    quotes: dict[str, dict] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for entry, quote_data, reason in pool.map(one, entries):
            if quote_data is None:
                log.warning("Kurs nicht verfügbar: %s (%s)", entry["name"], reason)
                failed.append(entry["name"])
            else:
                quotes[entry["symbol"]] = quote_data
    return quotes, failed


# ---------------------------------------------------------------- Texte

def market_summary(indices: list[dict], others: list[dict]) -> str:
    moved = [q for q in indices if q["change_1d"] is not None]
    if not moved:
        return ""
    up = sum(q["change_1d"] > 0 for q in moved)
    best = max(moved, key=lambda q: q["change_1d"])
    worst = min(moved, key=lambda q: q["change_1d"])
    if up == len(moved):
        mood = "Freundliche Börsen: alle beobachteten Indizes im Plus."
    elif up == 0:
        mood = "Schwache Börsen: alle beobachteten Indizes im Minus."
    else:
        mood = f"Gemischtes Bild: {up} von {len(moved)} Indizes im Plus."
    parts = [mood, f"Stärkster Markt: {best['name']} ({change_de(best['change_1d'])}), schwächster: {worst['name']} ({change_de(worst['change_1d'])})."]
    near_high = [q["name"] for q in indices + others if q["kind"] == "price" and q["from_high"] >= -1.0]
    if near_high:
        parts.append("Auf oder nahe am Jahreshoch: " + ", ".join(near_high) + ".")
    return " ".join(parts)


# ---------------------------------------------------------------- Nachrichtenbezug

def _company_pattern(company: dict) -> re.Pattern:
    if company.get("pattern"):
        return re.compile(company["pattern"])
    names = company.get("aliases") or [company["name"]]
    joined = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?<![\w-])(?:{joined})(?![\w])")


def _keyword_pattern(keywords: list[str]) -> re.Pattern | None:
    if not keywords:
        return None
    # Abkürzungen und kurze Wörter (EU, Fed, Zoll) nur in exakter Schreibweise, sonst egal
    exact = [re.escape(k) for k in keywords if k.isupper() or len(k) <= 4]
    loose = [re.escape(k) for k in keywords if not (k.isupper() or len(k) <= 4)]
    parts = []
    if exact:
        parts.append(rf"(?<!\w)(?:{'|'.join(exact)})(?!\w)")
    if loose:
        parts.append(rf"(?i:(?<!\w)(?:{'|'.join(loose)})(?!\w))")
    return re.compile("|".join(parts))


def _mentions(pattern: re.Pattern, exclude: re.Pattern | None, articles: list[Article]) -> list[Article]:
    found = []
    for article in articles:
        text = article.text
        if pattern.search(text) and not (exclude and exclude.search(text)):
            found.append(article)
    return found


def _related_stories(hits: list[Article], stories: list[Story], limit: int = 2) -> list[dict]:
    urls = {article.url for article in hits}
    related = []
    for story in stories:
        if any(article.url in urls for article in story.articles):
            link = next((safe_url(a.url) for a in story.articles if a.url in urls and safe_url(a.url)), None)
            if link:
                related.append({"title": story.title, "url": link})
        if len(related) >= limit:
            break
    return related


def watch_reasons(quote_data: dict, mentions: int, big_move: float) -> tuple[float, list[str]]:
    """Bewertet, wie beobachtenswert ein Unternehmen heute ist, und begründet es."""
    score, reasons = 0.0, []
    day = quote_data.get("change_1d")
    unusual = quote_data.get("unusual") or 0.0
    if day is not None and (abs(day) >= big_move or unusual >= 2.0):
        direction = "Kurssprung" if day > 0 else "Kursrutsch"
        extra = f", etwa {number_de(unusual, 0)}-mal so stark wie üblich" if unusual >= 2.0 else ""
        reasons.append(f"{direction} von {change_de(day)} an einem Handelstag{extra}")
        score += max(unusual, abs(day) / big_move * 2)
    month = quote_data.get("change_1m")
    if month is not None and abs(month) >= 15:
        reasons.append(f"{change_de(month)} in einem Monat")
        score += abs(month) / 15
    if quote_data.get("new_high"):
        reasons.append("Neues Jahreshoch")
        score += 1.5
    elif quote_data.get("new_low"):
        reasons.append("Neues Jahrestief")
        score += 1.5
    if mentions:
        reasons.append("In 1 Artikel von heute erwähnt" if mentions == 1 else f"In {mentions} Artikeln von heute erwähnt")
        score += 1.0 + min(mentions, 6) * 0.6
    return round(score, 2), reasons


# ---------------------------------------------------------------- Trends

def mention_history(data_dir: Path, today: date, days: int = 7) -> dict[str, list[int]]:
    """Erwähnungen je Trendthema aus den letzten Briefings im Archiv."""
    history: dict[str, list[int]] = {}
    if not data_dir.exists():
        return history
    for file in sorted(data_dir.iterdir(), reverse=True):
        if not DATE_FILE.match(file.name):
            continue
        day = date.fromisoformat(file.stem)
        if not (today - timedelta(days=days) <= day < today):
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for trend in (payload.get("markets") or {}).get("trends") or []:
            if isinstance(trend.get("mentions"), int):
                history.setdefault(trend.get("id", ""), []).append(trend["mentions"])
    return history


def trend_direction(mentions: int, past: list[int]) -> tuple[float | None, str]:
    if len(past) < 2:
        return None, ""
    average = _mean(past)
    if mentions >= max(average * 1.5, average + 3):
        return round(average, 1), "mehr als üblich"
    if mentions <= average * 0.6 and average - mentions >= 2:
        return round(average, 1), "weniger als üblich"
    return round(average, 1), "etwa wie üblich"


def build_trends(trends: list[dict], articles: list[Article], stories: list[Story], quotes: dict[str, dict],
                 history: dict[str, list[int]], limit: int) -> list[dict]:
    result = []
    for trend in trends:
        pattern = _keyword_pattern(trend.get("keywords") or [])
        hits = _mentions(pattern, None, articles) if pattern else []
        members = [quotes[s] for s in trend.get("symbols") or [] if s in quotes]
        month = [q["change_1m"] for q in members if q.get("change_1m") is not None and q["kind"] == "price"]
        week = [q["change_1w"] for q in members if q.get("change_1w") is not None and q["kind"] == "price"]
        average, direction = trend_direction(len(hits), history.get(trend["id"], []))
        basket_1m = round(_mean(month), 1) if month else None
        result.append({
            "id": trend["id"],
            "label": trend["label"],
            "mentions": len(hits),
            "average": average,
            "direction": direction,
            "basket_1w": round(_mean(week), 1) if week else None,
            "basket_1m": basket_1m,
            "members": [{"name": q["name"], "change_1m": q["change_1m"]} for q in members],
            "stories": _related_stories(hits, stories),
            "_rank": len(hits) * (1.5 if direction == "mehr als üblich" else 1.0) + abs(basket_1m or 0) / 4,
        })
    result.sort(key=lambda t: t["_rank"], reverse=True)
    for item in result:
        del item["_rank"]
    return [t for t in result if t["mentions"] or t["basket_1m"] is not None][:limit]


# ---------------------------------------------------------------- Gesamt

def build_markets(config: dict, articles: list[Article], stories: list[Story], data_dir: Path, today: date,
                  fetch: Fetcher | None = None) -> dict[str, Any]:
    markets = config["markets"]
    settings = config["settings"]
    fetch = fetch or yahoo_fetcher(settings, markets)
    groups_config = markets.get("groups") or []
    companies = markets.get("companies") or []
    entries = [entry for group in groups_config for entry in group["items"]] + companies
    quotes, failed = load_quotes(entries, fetch)
    minimum = int(markets.get("min_quotes", 5))
    if len(quotes) < minimum:
        log.warning("Börsenteil entfällt: nur %d Kurse geladen.", len(quotes))
        return {"available": False, "source": SOURCE_NOTE, "failed": failed}

    groups = []
    for group in groups_config:
        items = [quotes[e["symbol"]] for e in group["items"] if e["symbol"] in quotes]
        if items:
            groups.append({"label": group["label"], "items": items})
    index_quotes = groups[0]["items"] if groups else []
    other_quotes = [q for g in groups[1:] for q in g["items"]]

    big_move = float(markets.get("big_move_percent", 4))
    watch, overview = [], []
    for company in companies:
        quote_data = quotes.get(company["symbol"])
        if not quote_data:
            continue
        exclude = re.compile("|".join(re.escape(w) for w in company["exclude"])) if company.get("exclude") else None
        hits = _mentions(_company_pattern(company), exclude, articles)
        score, reasons = watch_reasons(quote_data, len(hits), big_move)
        compact = {k: quote_data[k] for k in ("symbol", "name", "unit", "decimals", "price", "change_1d", "change_1w",
                                              "change_1m", "change_ytd", "trend", "date")}
        compact["sector"] = company.get("sector", "")
        overview.append(compact)
        if reasons:
            watch.append(dict(compact, score=score, reasons=reasons, mentions=len(hits),
                              stories=_related_stories(hits, stories)))
    watch.sort(key=lambda item: item["score"], reverse=True)
    overview.sort(key=lambda item: item["name"].lower())

    history = mention_history(data_dir, today)
    trends = build_trends(markets.get("trends") or [], articles, stories, quotes, history, int(markets.get("max_trends", 6)))
    dates = sorted({q["date"] for q in quotes.values()})
    return {
        "available": True,
        "source": SOURCE_NOTE,
        "as_of": dates[-1] if dates else None,
        "summary": market_summary(index_quotes, other_quotes),
        "groups": groups,
        "watch": watch[: int(markets.get("max_watch", 6))],
        "companies": overview,
        "trends": trends,
        "failed": failed,
    }
