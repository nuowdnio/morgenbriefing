import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from briefing.models import Article, Source  # noqa: E402

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc)


def make_source(sid="a", region="europa", language="en", weight=1.0, lock=None, url="https://example.org/feed"):
    return Source(sid, sid.upper(), url, "Land", region, language, "privat", weight, True, lock)


def make_article(title="Titel", description="", url=None, source=None, hours_ago=1, categories=None):
    source = source or make_source()
    url = url or f"https://example.org/{abs(hash((title, source.id)))}"
    return Article(source, title, description, url, NOW - timedelta(hours=hours_ago), categories or [])


class EchoTranslator:
    """Ersetzt in Tests das echte Modell; markiert jede Übersetzung."""

    name = "Testübersetzer"

    def __init__(self):
        self.calls = []

    def prepare(self, source_languages, target):
        self.source_languages = source_languages

    def translate(self, text, source, target):
        if source == target:
            return text
        self.calls.append((text, source))
        return f"[de] {text}"


@pytest.fixture
def now():
    return NOW
