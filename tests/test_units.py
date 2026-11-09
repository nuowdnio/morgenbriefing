import numpy as np
import pytest

from briefing.cluster import cluster_articles
from briefing.embed import HashingEmbedder
from briefing.filters import apply_exclusions, deduplicate, within_window
from briefing.models import Story
from briefing.rank import diverse_order, score_story, select_stories
from briefing.summarize import select_sentences
from briefing.textutil import clean_text, normalize_url, safe_url, split_sentences, strip_kicker
from briefing.topics import TopicClassifier
from briefing.translate import GlossaryTranslator
from conftest import EchoTranslator, make_article, make_source

RANKING = {"sources": 3, "regions": 1.5, "recency": 1, "source_weight": 1, "recency_half_life_hours": 12}


# Escaping und Bereinigung
def test_clean_text_removes_markup_and_scripts():
    dirty = '<p>Gut &amp; sicher<script>alert(1)</script><img src=x onerror=alert(2)></p>'
    assert clean_text(dirty) == "Gut & sicher"


def test_clean_text_removes_feed_boilerplate():
    assert clean_text("Ein Satz. The post Foo appeared first on Bar.") == "Ein Satz."


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "ftp://x.org/a", "//x.org", "", None, "https://a b.org"])
def test_safe_url_rejects_bad_links(bad):
    assert safe_url(bad) is None


def test_safe_url_accepts_http_and_https():
    assert safe_url("https://example.org/a?b=1") == "https://example.org/a?b=1"
    assert safe_url("http://example.org") == "http://example.org"


def test_strip_kicker():
    assert strip_kicker("LOCAL ELECTIONS 2026: DA goes on offensive") == "DA goes on offensive"
    assert strip_kicker("Merz: Keine Reise nach Antalya") == "Merz: Keine Reise nach Antalya"


def test_split_sentences_handles_abbreviations():
    text = "Das gilt z.B. für Berlin. Der Etat steigt um 3,5 Prozent! Was folgt nun?"
    assert split_sentences(text) == ["Das gilt z.B. für Berlin.", "Der Etat steigt um 3,5 Prozent!", "Was folgt nun?"]


# Dubletten und Filter
def test_deduplicate_by_url_ignoring_tracking():
    one = make_article("A", url="https://www.x.org/n/1?utm_source=rss")
    two = make_article("B", url="https://x.org/n/1/?traffic_source=rss", hours_ago=2)
    assert deduplicate([two, one]) == [one]


def test_deduplicate_keeps_same_title_from_other_source():
    one = make_article("Gleich", source=make_source("a"), url="https://a.org/1")
    two = make_article("Gleich", source=make_source("b"), url="https://b.org/1")
    assert len(deduplicate([one, two])) == 2


def test_normalize_url_keeps_meaningful_query():
    assert normalize_url("https://x.org/a?id=4&utm_medium=x") == "https://x.org/a?id=4"


def test_window_and_exclusions(now):
    fresh = make_article("Neu", hours_ago=2, url="https://x.org/a")
    old = make_article("Alt", hours_ago=30, url="https://x.org/b")
    assert within_window([fresh, old], now, 24) == [fresh]
    ticker = make_article("Aktuelles", url="https://x.org/video/1")
    live = make_article("Live: Spiel", url="https://x.org/c")
    rules = {"title_patterns": ["^Live\\b"], "url_patterns": ["/video/"]}
    assert apply_exclusions([fresh, ticker, live], rules) == [fresh]


# Gruppierung
def test_cluster_groups_cross_language_vectors():
    articles = [make_article("Wahl in Israel"), make_article("Israel election"), make_article("Bundesliga")]
    vectors = np.array([[1.0, 0.05, 0], [0.98, 0.1, 0], [0, 0, 1.0]])
    stories = cluster_articles(articles, vectors / np.linalg.norm(vectors, axis=1, keepdims=True), 0.8)
    assert sorted(len(s.articles) for s in stories) == [1, 2]


def test_cluster_with_hashing_fallback_same_language():
    embedder = HashingEmbedder(0.35)
    articles = [
        make_article("Eisenkot gets mandate to form Israeli government", source=make_source("a")),
        make_article("Israel president gives Eisenkot mandate to form government", source=make_source("b")),
        make_article("Barcelona beat Atletico Madrid in La Liga", source=make_source("c")),
    ]
    stories = cluster_articles(articles, embedder.encode([a.title for a in articles]), embedder.threshold)
    assert sorted(len(s.articles) for s in stories) == [1, 2]


def test_cluster_handles_small_inputs():
    assert cluster_articles([], np.zeros((0, 3)), 0.6) == []
    assert len(cluster_articles([make_article()], np.ones((1, 3)), 0.6)) == 1


# Themen
TOPICS = [
    {"id": "weltpolitik", "label": "Weltpolitik", "keywords": ["Trump"], "path_hints": []},
    {"id": "sport", "label": "Sport", "keywords": ["Bundesliga"], "path_hints": ["/sport/"]},
    {"id": "technologie", "label": "Technologie", "keywords": ["KI"], "path_hints": []},
]


def classify(article):
    classifier = TopicClassifier(TOPICS, np.zeros((3, 2)))
    return classifier.assign(Story([article], [0]), np.ones((1, 2)))


def test_topic_by_url_path():
    assert classify(make_article("Ein Sieg", url="https://x.org/sport/1")) == "sport"


def test_topic_by_keyword_and_lock():
    assert classify(make_article("Neues aus der Bundesliga")) == "sport"
    assert classify(make_article("Ein Text", source=make_source(lock="technologie"))) == "technologie"


def test_acronym_keyword_is_case_sensitive():
    assert classify(make_article("Die Ki-Rolle ist unklar", url="https://x.org/1")) == "weltpolitik"
    assert classify(make_article("Neue KI vorgestellt", url="https://x.org/2")) == "technologie"


def test_unmatched_story_uses_fallback():
    assert classify(make_article("Etwas ohne Bezug")) == "weltpolitik"


# Gewichtung
def test_multiple_sources_outrank_single(now):
    single = Story([make_article(source=make_source("a"))])
    multi = Story([make_article(source=make_source("a")), make_article(source=make_source("b", region="asien"))])
    assert score_story(multi, now, RANKING, 1.0) > score_story(single, now, RANKING, 1.0)


def test_diversity_moves_other_region_forward():
    stories = []
    for index, (region, score) in enumerate([("europa", 10.0), ("europa", 9.9), ("europa", 9.8), ("afrika", 9.0)]):
        story = Story([make_article(f"T{index}", source=make_source(f"s{index}", region=region))])
        story.score = score
        stories.append(story)
    assert diverse_order(stories, 0.5)[1].primary_region == "afrika"


def test_topic_cap_and_total():
    stories = []
    for index in range(6):
        story = Story([make_article(f"T{index}", source=make_source(f"s{index}"))])
        story.score, story.topic = 10.0 - index, "sport" if index < 4 else "kultur"
        stories.append(story)
    selected = select_stories(stories, 0.0, 2, 3)
    assert [s.topic for s in selected].count("sport") == 2 and len(selected) == 3


# Zusammenfassung
def test_summary_only_uses_existing_sentences():
    description = "Der Bundestag beschloss am Montag den Haushalt mit 320 Stimmen. Die Opposition stimmte geschlossen dagegen."
    story = Story([make_article("Haushalt beschlossen", description, source=make_source(language="de"))])
    sentences, language = select_sentences(story, "Haushalt beschlossen", "de", 3, 480)
    assert language == "de" and sentences and all(s in description for s in sentences)


def test_summary_removes_near_duplicates_and_prefers_target_language():
    german = make_article("Titel", "Die Regierung kündigte am Montag neue Hilfen für betroffene Familien an.", source=make_source("a", language="de"))
    german2 = make_article("Titel", "Die Regierung kündigte am Montag neue Hilfen für alle betroffenen Familien an.", source=make_source("b", language="de"))
    english = make_article("Title", "The government announced fresh aid for affected families on Monday.", source=make_source("c", language="en"))
    sentences, language = select_sentences(Story([german, german2, english]), "Etwas anderes", "de", 3, 480)
    assert language == "de" and len(sentences) == 1


def test_summary_empty_without_description():
    assert select_sentences(Story([make_article("Nur Titel")]), "Nur Titel", "de", 3, 480) == ([], None)


# Glossar
def glossary(inner):
    return GlossaryTranslator(inner, {"keep": ["Merz"], "replace": {"Netanyahu": "Netanjahu"}})


def test_glossary_protects_terms_and_post_edits():
    translator = glossary(EchoTranslator())
    assert translator.translate("Merz met Netanyahu", "en", "de") == "[de] Merz met Netanjahu"


def test_glossary_retries_when_placeholder_is_damaged():
    class Damaging(EchoTranslator):
        def translate(self, text, source, target):
            self.calls.append(text)
            return text.replace("XQ0QX", "xq 0 qx")

    inner = Damaging()
    assert glossary(inner).translate("Merz spoke", "en", "de") == "Merz spoke"
    assert len(inner.calls) == 2


def test_glossary_skips_same_language():
    inner = EchoTranslator()
    assert glossary(inner).translate("Merz sprach", "de", "de") == "Merz sprach" and not inner.calls
