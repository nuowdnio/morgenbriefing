"""Bereinigung von Feed-Inhalten. Feed-Daten gelten als nicht vertrauenswürdig."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING = re.compile(r"^(utm_|at_|ref$|ref_|traffic_source$|fbclid$|gclid$|ocid$)", re.I)
_BOILERPLATE = re.compile(
    r"(The post .* appeared first on .*|Read more\b.*|Continue reading.*|Weiterlesen.*|mehr\.\.\.|Mehr lesen.*|\[…\]|\[\.\.\.\])\s*$",
    re.I | re.S,
)
_KICKER = re.compile(r"^(?:[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9 ,'’&./-]{3,}):\s+(?=\S)")
_ABBREVIATION_AT_END = re.compile(
    r"(?:^|[\s(])(?:z\.\s?B|d\.\s?h|u\.\s?a|v\.\s?a|bzw|ca|Dr|Prof|Nr|St|Mr|Mrs|Ms|vs|etc|U\.S|Jan|Feb|Apr|Aug|Sept?|Okt|Oct|Nov|Dez|Dec)\.$"
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])[\"“”'’»)]*\s+(?=[\"„“'«(]?[A-ZÄÖÜ0-9])")


class _Stripper(HTMLParser):
    _SKIP = {"script", "style", "iframe", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.depth += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def clean_text(value: str | None) -> str:
    """Entfernt HTML, Entities, Steuerzeichen und Feed-Floskeln."""
    if not value:
        return ""
    stripper = _Stripper()
    stripper.feed(value)
    stripper.close()
    text = html.unescape("".join(stripper.parts))
    text = re.sub(r"[\u0000-\u001f\u007f-\u009f​-‏ -‮⁠-⁯]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _BOILERPLATE.sub("", text).strip()


def strip_kicker(title: str) -> str:
    """Entfernt Dachzeilen in Großbuchstaben wie 'LOCAL ELECTIONS 2026: ...'."""
    return _KICKER.sub("", title).strip()


def safe_url(value: str | None) -> str | None:
    """Lässt nur saubere http(s)-Adressen zu."""
    if not value:
        return None
    value = value.strip()
    if any(ord(ch) < 33 for ch in value):
        return None
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return None
    return value


def normalize_url(value: str) -> str:
    parts = urlsplit(value)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = parts.path.rstrip("/")
    return urlunsplit(("https", parts.netloc.lower().removeprefix("www."), path, query, ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[^\w ]+", "", title.casefold()).strip()


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        before = text[start:match.start()]
        if _ABBREVIATION_AT_END.search(before):
            continue
        sentences.append(text[start:match.end()].strip())
        start = match.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def word_set(text: str) -> set[str]:
    return {word for word in re.findall(r"\w+", text.casefold()) if len(word) > 3}


def jaccard(left: str, right: str) -> float:
    a, b = word_set(left), word_set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
