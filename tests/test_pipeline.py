"""Ende-zu-Ende-Test mit lokalem Webserver, echtem RSS-Parser und Testübersetzer."""
import copy
import json
import random
import re
import threading
from datetime import timedelta
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from briefing.config import build_sources
from briefing.embed import HashingEmbedder
from briefing.output import write_briefing
from briefing.pipeline import BriefingError, run_pipeline
from conftest import NOW, EchoTranslator

ROOT = Path(__file__).resolve().parents[1]


def rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link><description><![CDATA[{d}]]></description>"
        f"<pubDate>{format_datetime(NOW - timedelta(hours=h))}</pubDate></item>"
        for t, link, d, h in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class Site:
    def __init__(self):
        self.pages = {}
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status, body = site.pages.get(self.path, (404, b""))
                self.send_response(status)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def site():
    server = Site()
    yield server
    server.server.shutdown()


def world_items(tag, shared):
    items = [
        ("Israel president gives Eisenkot mandate to form government", f"https://{tag}.example/eisenkot",
         "Herzog gave opposition leader Gadi Eisenkot the mandate on Saturday. Neither side won a majority in the vote.", 3),
    ] if shared else []
    for number in range(8):
        rng = random.Random(f"{tag}-{number}")
        words = [
            "".join(rng.choice("bcdfghklmnprstvwz") + rng.choice("aeiou") for _ in range(4))
            for _ in range(24)
        ]
        items.append((f"{' '.join(words[:8])} marker{number}", f"https://{tag}.example/report{number}",
                      f"{' '.join(words[8:16]).capitalize()} useful sentence. {' '.join(words[16:24]).capitalize()} has 42 details.", 2 + number))
    return items


def build_config(site, count=6, min_ok=4, min_stories=5):
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["settings"].update(min_sources_ok=min_ok, min_stories=min_stories, request_timeout_seconds=5)
    config["markets"]["enabled"] = False
    regions = ["europa", "asien", "afrika", "nordamerika", "nahost", "lateinamerika"]
    config["sources"] = [
        {"id": f"s{i}", "name": f"Quelle {i}", "url": f"{site.base}/feed{i}.xml", "country": "Land",
         "region": regions[i % 6], "language": "en", "ownership": "privat", "weight": 1.0, "enabled": True}
        for i in range(count)
    ]
    return config


def populate(site, count=6):
    site.pages["/robots.txt"] = (404, b"")
    for i in range(count):
        site.pages[f"/feed{i}.xml"] = (200, rss(world_items(f"s{i}", shared=True)))


def run(site, tmp_path, config):
    return run_pipeline(config, build_sources(config), EchoTranslator(), HashingEmbedder(0.35), tmp_path, now=NOW)


def test_full_run_writes_valid_briefing(site, tmp_path):
    populate(site)
    payload = run(site, tmp_path, build_config(site))
    assert payload["date"] == "2026-11-09"
    assert (tmp_path / "2026-11-09.json").exists()
    assert json.loads((tmp_path / "index.json").read_text())["dates"] == ["2026-11-09"]
    grouped = [s for s in payload["stories"] if "Eisenkot" in s["title"]]
    assert len(grouped) == 1 and grouped[0]["source_count"] == 6 and not grouped[0]["single_source"]
    assert payload["stories"][0] == grouped[0]
    assert all(s["title"].startswith("[de] ") and s["machine_translated"] for s in payload["stories"])
    singles = [s for s in payload["stories"] if s["source_count"] == 1]
    assert singles and all(s["single_source"] for s in singles)
    assert all(len(s["links"]) == s["source_count"] for s in payload["stories"])


def test_malicious_feed_content_is_neutralized(site, tmp_path):
    populate(site)
    attack = [("Bad &lt;img src=x onerror=alert(1)&gt; headline harbour", "javascript:alert(1)", "desc", 1),
              ("Harmless markup story about bridges <b>bold</b>", "https://evil.example/ok",
               '<script>alert(2)</script>A readable sentence that is long enough to keep here.<a href="javascript:x">y</a>', 1)]
    site.pages["/feed0.xml"] = (200, rss(attack + world_items("s0", shared=True)))
    run(site, tmp_path, build_config(site))
    raw = (tmp_path / "2026-11-09.json").read_text(encoding="utf-8")
    assert "javascript:" not in raw and "<script" not in raw and "<b>" not in raw


def test_failed_source_is_reported_and_run_continues(site, tmp_path):
    populate(site)
    site.pages["/feed1.xml"] = (500, b"")
    payload = run(site, tmp_path, build_config(site))
    failed = [s for s in payload["sources"] if not s["ok"]]
    assert [s["name"] for s in failed] == ["Quelle 1"] and "HTTP 500" in failed[0]["reason"]


def test_robots_exclusion_is_respected(site, tmp_path):
    populate(site)
    site.pages["/robots.txt"] = (200, b"User-agent: *\nDisallow: /feed2.xml\n")
    payload = run(site, tmp_path, build_config(site))
    assert [s["name"] for s in payload["sources"] if not s["ok"]] == ["Quelle 2"]
    assert "robots" in [s for s in payload["sources"] if not s["ok"]][0]["reason"]


def test_too_few_sources_keeps_previous_briefing(site, tmp_path):
    populate(site, 2)
    previous = tmp_path / "2026-11-08.json"
    previous.write_text("{}", encoding="utf-8")
    with pytest.raises(BriefingError):
        run(site, tmp_path, build_config(site, count=2))
    assert previous.read_text() == "{}" and not (tmp_path / "2026-11-09.json").exists()


def test_failed_translation_drops_only_that_story(site, tmp_path):
    class Flaky(EchoTranslator):
        def translate(self, text, source, target):
            if "marker3" in text:
                raise RuntimeError("kaputt")
            return super().translate(text, source, target)

    populate(site)
    config = build_config(site)
    payload = run_pipeline(config, build_sources(config), Flaky(), HashingEmbedder(0.35), tmp_path, now=NOW)
    assert payload["stories"] and not any("marker3" in s["title"] for s in payload["stories"])


def test_archive_keeps_30_days(tmp_path):
    from datetime import date

    for offset in range(35):
        write_briefing(tmp_path, date(2026, 11, 9) - timedelta(days=34 - offset), {"x": 1}, 30)
    dates = json.loads((tmp_path / "index.json").read_text())["dates"]
    assert len(dates) == 30 and dates[0] == "2026-11-09" and dates[-1] == "2026-10-11"


def test_project_uses_no_keys_or_paid_services():
    forbidden = re.compile(
        r"api[_-]?key|secrets\.|authorization:|bearer\s|x-api-|api\.openai\.com|api\.anthropic\.com|"
        r"deepl\.com|translate\.googleapis|translation\.googleapis|translator\.microsoft|cognitive\.microsofttranslator",
        re.IGNORECASE,
    )
    this_file = Path(__file__).resolve()
    suffixes = {".py", ".yml", ".yaml", ".js", ".html", ".txt"}
    hits = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix in suffixes and path.resolve() != this_file
        and ".git/" not in path.as_posix() and "/site/data/" not in path.as_posix()
        and forbidden.search(_without_allowed(path))
    ]
    assert hits == []


# Einzige erlaubte Ausnahme: Der Knopf "Briefing neu erstellen" schickt den Token, den der Nutzer
# selbst im Browser eingibt, an GitHub. Im Projekt selbst steht kein Schlüssel.
ALLOWED = {"site/app.js": ['Authorization: "Bearer " + token(),']}


def _without_allowed(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    for snippet in ALLOWED.get(path.relative_to(ROOT).as_posix(), []):
        text = text.replace(snippet, "")
    return text


def test_browser_token_only_goes_to_github():
    app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert app.count('Authorization: "Bearer " + token()') == 1
    assert 'const API = "https://api.github.com/repos/";' in app and "fetch(base + path" in app
    assert re.search(r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{20,}", app + html) is None
    assert "connect-src 'self' https://api.github.com;" in html


def test_run_with_markets_adds_section_and_survives_outage(site, tmp_path):
    from test_markets import chart, wavy

    populate(site)
    config = build_config(site)
    config["markets"]["enabled"] = True
    payload = run_pipeline(config, build_sources(config), EchoTranslator(), HashingEmbedder(0.35), tmp_path, now=NOW,
                           market_fetch=lambda symbol: chart(wavy()))
    markets = json.loads((tmp_path / "2026-11-09.json").read_text())["markets"]
    assert markets["available"] and markets["groups"][0]["label"] == "Aktienindizes"
    assert payload["stories"]

    def down(symbol):
        raise ConnectionError("weg")

    payload = run_pipeline(config, build_sources(config), EchoTranslator(), HashingEmbedder(0.35), tmp_path, now=NOW,
                           market_fetch=down)
    assert payload["markets"]["available"] is False and payload["stories"]
