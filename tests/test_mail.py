from datetime import datetime

from briefing.mail_issue import build_body, escape, german_date
from briefing.main import is_too_early


def payload():
    story = {"rank": 1, "topic": "klima", "title": "A", "summary": ["B."], "single_source": True,
             "links": [{"source": "Q", "url": "https://x.org/a_(b)"}, {"source": "Bad", "url": "javascript:alert(1)"}]}
    others = [dict(story, rank=i, topic="sport" if i % 2 else "klima", title=f"T{i}", single_source=False) for i in range(2, 9)]
    return {"date": "2026-11-09", "top_count": 2, "topics": [{"id": "klima", "label": "Klima"}, {"id": "sport", "label": "Sport"}],
            "stories": [story] + others}


def test_feed_text_cannot_mention_or_format():
    assert "@elonmusk" not in escape("Hallo @elonmusk") and "#12" not in escape("siehe #12")
    assert escape("<img src=x> *fett* [l](u)") == r"\<img src=x\> \*fett\* \[l\](u)"


def test_body_mentions_owner_only_once_and_lists_top_first():
    body = build_body(payload(), "nuowdnio", "https://nuowdnio.github.io/morgenbriefing/")
    assert body.count("@") == 1 and "@" not in escape(body.split("!", 1)[1]).replace("@\u200b", "") and body.startswith("Guten Morgen @nuowdnio!")
    assert body.index("Das Wichtigste") < body.index("## Klima") < body.index("## Sport")
    assert "Montag, 9. November 2026" in body and "nuowdnio.github.io/morgenbriefing/" in body


def test_body_drops_bad_links_and_encodes_brackets():
    body = build_body(payload(), "o", "https://o.github.io/r/")
    assert "javascript:" not in body and "https://x.org/a_%28b%29" in body and "(nur eine Quelle)" in body


def test_body_respects_topic_choice_and_length():
    body = build_body(payload(), "o", "https://o.github.io/r/", topics=["klima"])
    assert "## Sport" not in body
    short = build_body(payload(), "o", "https://o.github.io/r/", max_chars=700)
    assert len(short) <= 760 and "Alle weiteren Meldungen" in short


def test_german_date():
    assert german_date("2026-12-24") == "Donnerstag, 24. Dezember 2026"


def test_not_before_time():
    assert is_too_early(datetime(2026, 1, 1, 4, 40), "05:00")
    assert not is_too_early(datetime(2026, 1, 1, 5, 40), "05:00")
    assert not is_too_early(datetime(2026, 1, 1, 4, 40), None)
