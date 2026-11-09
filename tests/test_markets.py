"""Börsenteil: Kennzahlen, Auswahl auffälliger Unternehmen, Trends, Ausfallsicherheit."""
import json
import re
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from briefing.config import ConfigError, validate_markets
from briefing.mail_issue import build_body, markets_block
from briefing.markets import (build_markets, mention_history, parse_chart, quote_metrics, trend_direction,
                              watch_reasons)
from briefing.numbers import change_de, number_de
from briefing.models import Story
from briefing.pipeline import markets_section
from conftest import make_article

TODAY = date(2026, 11, 9)


def chart(closes, currency="EUR", end=date(2026, 11, 6)):
    """Baut eine Antwort im Format der Chart-Schnittstelle (nur Handelstage)."""
    days, day = [], end
    while len(days) < len(closes):
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    days.reverse()
    stamps = [int(datetime(d.year, d.month, d.day, 15, tzinfo=timezone.utc).timestamp()) for d in days]
    return {"chart": {"result": [{"meta": {"currency": currency}, "timestamp": stamps,
                                  "indicators": {"quote": [{"close": list(closes)}]}}]}}


def wavy(n=260, start=100.0, drift=0.0005, last=None):
    closes = [start * (1 + drift) ** i * (1 + 0.01 * math.sin(i)) for i in range(n)]
    if last is not None:
        closes[-1] = closes[-2] * (1 + last / 100)
    return closes


def config(companies=None, trends=None):
    return {
        "settings": {"user_agent": "test", "request_timeout_seconds": 5},
        "markets": {
            "enabled": True, "big_move_percent": 4, "max_watch": 3, "max_trends": 4, "min_quotes": 2,
            "groups": [
                {"label": "Aktienindizes", "items": [{"symbol": "^A", "name": "Index A", "unit": "Pkt."},
                                                     {"symbol": "^B", "name": "Index B", "unit": "Pkt."}]},
                {"label": "Zinsen", "items": [{"symbol": "^TNX", "name": "Rendite", "unit": "%", "kind": "yield", "decimals": 2}]},
            ],
            "companies": companies if companies is not None else [
                {"symbol": "JUMP", "name": "Springer AG", "sector": "Technik", "aliases": ["Springer"]},
                {"symbol": "CALM", "name": "Ruhig AG", "sector": "Chemie", "aliases": ["Ruhig AG"]},
                {"symbol": "NEWS", "name": "Amazon", "sector": "Handel", "aliases": ["Amazon"], "exclude": ["Regenwald"]},
            ],
            "trends": trends if trends is not None else [
                {"id": "ki", "label": "KI", "keywords": ["KI", "künstliche Intelligenz"], "symbols": ["JUMP"]},
                {"id": "zins", "label": "Zinsen", "keywords": ["Fed", "Leitzins"], "symbols": ["^TNX"]},
            ],
        },
    }


def fetcher(data):
    def fetch(symbol):
        if symbol not in data:
            raise ConnectionError("weg")
        return data[symbol]
    return fetch


def market_data():
    return {
        "^A": chart(wavy(last=1.2)), "^B": chart(wavy(drift=-0.0004, last=-0.8), currency="USD"),
        "^TNX": chart([4.0 + i * 0.001 for i in range(260)], currency="USD"),
        "JUMP": chart(wavy(last=9.0)), "CALM": chart(wavy(last=0.1)), "NEWS": chart(wavy(last=0.2)),
    }


def test_parse_chart_skips_gaps_and_metrics_are_plausible():
    data = chart([10.0, None, 11.0, float("nan"), 12.1])
    meta, series = parse_chart(data)
    assert [close for _, close in series] == [10.0, 11.0, 12.1] and meta["currency"] == "EUR"
    metrics = quote_metrics({"symbol": "X", "name": "X"}, meta, series)
    assert metrics["change_1d"] == 10.0 and metrics["unit"] == "€" and metrics["new_high"] is False


def test_year_change_uses_last_close_of_previous_year():
    _, series = parse_chart(chart(wavy(n=260)))
    metrics = quote_metrics({"symbol": "X", "name": "X"}, {}, series)
    base = [c for d, c in series if d.year < 2026][-1]
    assert metrics["change_ytd"] == round((series[-1][1] / base - 1) * 100, 2)
    assert metrics["trend"] in {"Aufwärtstrend", "Abwärtstrend", "uneinheitlich"} and len(metrics["spark"]) == 60


def test_yield_changes_are_in_percentage_points():
    _, series = parse_chart(chart([4.0, 4.25]))
    metrics = quote_metrics({"symbol": "^TNX", "name": "R", "kind": "yield"}, {}, series)
    assert metrics["change_1d"] == 0.25 and metrics["kind"] == "yield"
    assert change_de(0.25, absolute=True) == "+0,25 Pp."


def test_german_number_format():
    assert number_de(24312.456, 0) == "24.312" and number_de(1.08234, 4) == "1,0823" and number_de(-3.5, 1) == "−3,5"
    assert change_de(-1.234) == "−1,2 %" and change_de(0.0) == "±0,0 %" and change_de(None) == "–"


def test_watch_reasons_explain_selection():
    score, reasons = watch_reasons({"change_1d": 9.0, "unusual": 6.3, "change_1m": 20.0, "new_high": True}, 3, 4)
    assert score > 5 and reasons[0].startswith("Kurssprung von +9,0 %") and "6-mal" in reasons[0]
    assert "Neues Jahreshoch" in reasons and "In 3 Artikeln von heute erwähnt" in reasons
    assert watch_reasons({"change_1d": 0.3, "unusual": 0.2, "change_1m": 1.0}, 0, 4) == (0.0, [])


def test_build_markets_selects_movers_and_news_companies(tmp_path):
    springer = make_article("Springer startet neue KI-Plattform", "Die künstliche Intelligenz soll helfen.")
    rainforest = make_article("Amazon: Regenwald schrumpft weiter", "Neue Daten zum Regenwald.")
    shopping = make_article("Amazon baut Lager in Sachsen", "Der Konzern investiert.")
    fed = make_article("Fed lässt den Leitzins unverändert", "Die Notenbank wartet ab.")
    articles = [springer, rainforest, shopping, fed, make_article("Die Kinder waren fed up", "nichts")]
    story = Story([springer], title="Springer startet KI-Plattform")
    result = build_markets(config(), articles, [story], tmp_path, TODAY, fetcher(market_data()))

    assert result["available"] and result["as_of"] == "2026-11-06"
    assert [g["label"] for g in result["groups"]] == ["Aktienindizes", "Zinsen"]
    assert "1 von 2 Indizes im Plus" in result["summary"] and "Index A" in result["summary"]
    names = [w["name"] for w in result["watch"]]
    assert names[0] == "Springer AG" and "Ruhig AG" not in names
    assert result["watch"][0]["stories"] == [{"title": "Springer startet KI-Plattform", "url": springer.url}]
    amazon = next(w for w in result["watch"] if w["name"] == "Amazon")
    assert amazon["mentions"] == 1
    assert len(result["companies"]) == 3
    trends = {t["id"]: t for t in result["trends"]}
    assert trends["ki"]["mentions"] == 1 and trends["ki"]["basket_1m"] is not None
    assert trends["zins"]["mentions"] == 1 and trends["zins"]["basket_1m"] is None  # Renditen zählen nicht als Kursplus
    json.dumps(result)


def test_trend_history_from_archive(tmp_path):
    for offset, count in enumerate([2, 3, 2, 3], start=1):
        day = TODAY - timedelta(days=offset)
        payload = {"markets": {"trends": [{"id": "ki", "mentions": count}]}}
        (tmp_path / f"{day.isoformat()}.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / f"{TODAY.isoformat()}.json").write_text(json.dumps({"markets": {"trends": [{"id": "ki", "mentions": 99}]}}))
    (tmp_path / "2026-11-01.json").write_text("kaputt")
    history = mention_history(tmp_path, TODAY)
    assert sorted(history["ki"]) == [2, 2, 3, 3]
    assert trend_direction(9, history["ki"]) == (2.5, "mehr als üblich")
    assert trend_direction(2, history["ki"])[1] == "etwa wie üblich"
    assert trend_direction(5, [1]) == (None, "")


def test_missing_quotes_drop_only_markets_section(tmp_path):
    result = build_markets(config(), [], [], tmp_path, TODAY, fetcher({"^A": chart(wavy())}))
    assert result["available"] is False and "Index B" in result["failed"]

    def broken(symbol):
        raise RuntimeError("Totalausfall")

    cfg = config()
    assert markets_section(cfg, [], [], tmp_path, TODAY, broken)["available"] is False
    cfg["markets"]["enabled"] = False
    assert markets_section(cfg, [], [], tmp_path, TODAY, broken) is None


def test_hostile_market_names_are_escaped_in_mail(tmp_path):
    cfg = config(companies=[{"symbol": "JUMP", "name": "Evil @user *x*", "sector": "T", "aliases": ["Evil"]}], trends=[])
    article = make_article("Evil kündigt etwas an", "", url="https://e.org/a_(b)")
    markets = build_markets(cfg, [article], [Story([article], title="[Klick](javascript:x)")], tmp_path, TODAY,
                            fetcher(market_data()))
    block = markets_block(markets, "https://o.github.io/r/")
    assert "@user" not in block and "\\*x\\*" in block and not re.search(r"(?<!\\)\]\(javascript", block) and "\\[Klick\\]" in block
    assert "https://e.org/a_%28b%29" in block and "| Index A |" in block and "Keine Anlageberatung" in block


def test_mail_keeps_markets_even_when_news_are_long(tmp_path):
    markets = build_markets(config(), [], [], tmp_path, TODAY, fetcher(market_data()))
    story = {"rank": 1, "topic": "klima", "title": "A" * 400, "summary": ["B" * 400], "single_source": False, "links": []}
    payload = {"date": "2026-11-09", "top_count": 3, "topics": [{"id": "klima", "label": "Klima"}],
               "stories": [dict(story, rank=i) for i in range(1, 40)], "markets": markets}
    body = build_body(payload, "o", "https://o.github.io/r/", max_chars=8000)
    assert len(body) <= 8000 and "## Börse & Märkte" in body and "Alle weiteren Meldungen" in body
    assert "## Börse & Märkte" not in build_body(payload, "o", "https://o.github.io/r/", markets=False)
    unavailable = dict(payload, markets={"available": False})
    assert "nicht abrufbar" in build_body(unavailable, "o", "https://o.github.io/r/")


def test_market_config_is_checked():
    good = config()["markets"]
    validate_markets(good)
    bad = json.loads(json.dumps(good))
    bad["trends"][0]["symbols"] = ["GIBTSNICHT"]
    with pytest.raises(ConfigError):
        validate_markets(bad)
    bad = json.loads(json.dumps(good))
    bad["companies"].append(dict(bad["companies"][0]))
    with pytest.raises(ConfigError):
        validate_markets(bad)


def test_real_config_companies_match_sensibly():
    import re
    from pathlib import Path

    import yaml

    from briefing.markets import _company_pattern

    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8"))
    companies = {c["name"]: c for c in cfg["markets"]["companies"]}
    siemens = _company_pattern(companies["Siemens"])
    assert siemens.search("Siemens baut Stellen ab") and not siemens.search("Siemens Energy hebt Prognose an")
    assert _company_pattern(companies["Siemens Energy"]).search("Siemens Energy hebt Prognose an")
    assert not _company_pattern(companies["Meta"]).search("eine meta-Debatte")
    assert re.search("|".join(companies["Amazon"]["exclude"]), "Amazon rainforest loss slows")


def test_mail_module_needs_only_yaml():
    import subprocess
    import sys
    code = "import sys; sys.modules['requests'] = None; import briefing.mail_issue"
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    assert subprocess.run([sys.executable, "-c", code], cwd=root).returncode == 0
