"""Lokale, austauschbare Übersetzer. Es werden keine Online-Übersetzungsdienste benutzt."""
from __future__ import annotations

import logging
import re
from typing import Protocol

log = logging.getLogger(__name__)


class TranslationError(RuntimeError):
    pass


class Translator(Protocol):
    name: str

    def prepare(self, source_languages: set[str], target: str) -> None: ...

    def translate(self, text: str, source: str, target: str) -> str: ...


class ArgosTranslator:
    name = "Argos Translate"

    def prepare(self, source_languages: set[str], target: str) -> None:
        import argostranslate.package as package

        pairs: set[tuple[str, str]] = set()
        for language in source_languages - {target}:
            if language == "en" or target == "en":
                pairs.add((language, target))
            else:
                pairs.update({(language, "en"), ("en", target)})
        installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
        missing = pairs - installed
        if not missing:
            return
        package.update_package_index()
        available = {(p.from_code, p.to_code): p for p in package.get_available_packages()}
        for pair in sorted(missing):
            if pair not in available:
                raise TranslationError(f"Kein Argos-Modell für {pair[0]} nach {pair[1]} verfügbar.")
            log.info("Lade Argos-Modell %s -> %s", *pair)
            package.install_from_path(available[pair].download())

    def translate(self, text: str, source: str, target: str) -> str:
        import argostranslate.translate as argos

        return argos.translate(text, source, target)


class OpusTranslator:
    """Helsinki-NLP Opus-MT (frei nutzbar, lokal). Derzeit nur Englisch nach Deutsch."""

    name = "Opus-MT"
    model_name = "Helsinki-NLP/opus-mt-en-de"

    def __init__(self) -> None:
        self.tokenizer = None
        self.model = None

    def prepare(self, source_languages: set[str], target: str) -> None:
        unsupported = source_languages - {target, "en"}
        if target != "de" or unsupported:
            raise TranslationError("Opus-MT ist hier nur für Englisch nach Deutsch eingerichtet.")
        from transformers import MarianMTModel, MarianTokenizer

        self.tokenizer = MarianTokenizer.from_pretrained(self.model_name)
        self.model = MarianMTModel.from_pretrained(self.model_name)

    def translate(self, text: str, source: str, target: str) -> str:
        batch = self.tokenizer([text], return_tensors="pt", truncation=True, max_length=400)
        output = self.model.generate(**batch, max_new_tokens=400)
        return self.tokenizer.decode(output[0], skip_special_tokens=True)


def build_translator(name: str) -> Translator:
    if name == "argos":
        return ArgosTranslator()
    if name == "opus":
        return OpusTranslator()
    raise TranslationError(f"Unbekannter Übersetzer: {name}")


class GlossaryTranslator:
    """Schützt feste Namen und korrigiert Begriffe nach der Übersetzung."""

    def __init__(self, inner: Translator, glossary: dict) -> None:
        self.inner = inner
        self.name = inner.name
        self.keep = sorted(glossary.get("keep", []), key=len, reverse=True)
        self.replacements = glossary.get("replace", {})

    def prepare(self, source_languages: set[str], target: str) -> None:
        self.inner.prepare(source_languages, target)

    def _protect(self, text: str) -> tuple[str, dict[str, str]]:
        mapping: dict[str, str] = {}
        for term in self.keep:
            pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")
            if not pattern.search(text):
                continue
            token = f"XQ{len(mapping)}QX"
            mapping[token] = term
            text = pattern.sub(token, text)
        return text, mapping

    def _post_edit(self, text: str) -> str:
        for wrong, right in self.replacements.items():
            text = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, text)
        return text.strip()

    def translate(self, text: str, source: str, target: str) -> str:
        if source == target:
            return text
        protected, mapping = self._protect(text)
        result = self.inner.translate(protected, source, target)
        if mapping and not all(token in result for token in mapping):
            # Das Modell hat einen Platzhalter verändert: ohne Schutz neu übersetzen.
            result = self.inner.translate(text, source, target)
        else:
            for token, term in mapping.items():
                result = result.replace(token, term)
        if not result or not result.strip():
            raise TranslationError("Leere Übersetzung erhalten.")
        return self._post_edit(result)
