"""Deterministic learner lookup and immutable saved-word lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from vocab_lexical_engine import (
    active_dataset_status,
    canonical_json,
    evidence_set_hash,
    lookup,
    resolve_active_database,
)


CORE_MEANING_LIMIT = 5
US_PRONUNCIATION_TAGS = frozenset({"US", "General-American"})
SENSE_RELATION_TYPES = (
    "synonyms", "antonyms", "related", "derived", "hypernyms", "hyponyms",
)


@dataclass
class LexicalState:
    query: str
    candidate: dict[str, Any] | None = None
    saved_version: dict[str, Any] | None = None
    origin: str = "search"
    refresh_available: bool = False
    dataset_status_error: str | None = None
    failure: dict[str, Any] | None = None

    @property
    def actions(self) -> dict[str, bool]:
        valid = self.candidate is not None and self.failure is None
        saved = self.saved_version is not None and self.origin == "saved"
        return {
            "save": valid and not saved,
            "refresh": valid and saved and self.refresh_available,
            "flag": valid,
        }


def _source_order(entry: dict[str, Any]) -> tuple[str, int, str]:
    locator = str(entry.get("source_locator") or "")
    source_path, marker, line = locator.partition("#line=")
    if marker and line.isdigit():
        return source_path, int(line), entry.get("entry_key", "")
    return source_path or locator, 0, entry.get("entry_key", "")


def _sense_relations(
    sense: dict[str, Any], sense_id: str, entry: dict[str, Any]
) -> list[dict[str, Any]]:
    relations = []
    for relation_type in SENSE_RELATION_TYPES:
        for relation in sense.get(relation_type, []):
            target = relation.get("word") if isinstance(relation, dict) else relation
            if not target:
                continue
            relations.append({
                "evidence_id": (
                    f"SRC:{sense_id}:{relation_type}:"
                    f"{hashlib.sha256(canonical_json(relation).encode()).hexdigest()[:24]}"
                ),
                "type": relation_type,
                "target": str(target),
                "source": relation,
                "source_locator": entry.get("source_locator"),
            })
    return relations


def _project_source_evidence(result: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for entry in sorted(result.get("entries", []), key=_source_order):
        source = json.loads(entry["source_record_json"])
        senses = []
        for normalized_sense in entry.get("senses", []):
            source_order = normalized_sense["source_order"]
            source_senses = source.get("senses", [])
            source_sense = source_senses[source_order - 1] if source_order <= len(source_senses) else {}
            senses.append({
                "sense_id": normalized_sense["sense_id"],
                "source_order": source_order,
                "glosses": normalized_sense.get("glosses", []),
                "raw_glosses": source_sense.get("raw_glosses", []),
                "tags": normalized_sense.get("tags", []),
                "topics": source_sense.get("topics", []),
                "examples": source_sense.get("examples", []),
                "relations": _sense_relations(source_sense, normalized_sense["sense_id"], entry),
                "form_of": source_sense.get("form_of", []),
                "alt_of": source_sense.get("alt_of", []),
            })
        entries.append({
            "entry_key": entry["entry_key"],
            "word": entry["word"],
            "part_of_speech": entry["part_of_speech"],
            "dataset_version": entry["dataset_version"],
            "importer_version": entry["importer_version"],
            "source_locator": entry["source_locator"],
            "source_record_hash": entry["source_record_hash"],
            "etymology_number": source.get("etymology_number"),
            "etymology": {
                "text": source.get("etymology_text"),
                "templates": source.get("etymology_templates", []),
            },
            "forms": source.get("forms", []),
            "sounds": source.get("sounds", []),
            "senses": senses,
        })
    return {
        "schema_version": "deterministic-lexical-evidence-v1",
        "normalized_lemma": result.get("word", "").casefold(),
        "wiktionary_versions": sorted({
            entry["dataset_version"] for entry in entries
        }),
        "entries": entries,
    }


def _source_meanings(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    meanings = []
    for entry in evidence["entries"]:
        for sense in entry["senses"]:
            glosses = sense.get("glosses") or sense.get("raw_glosses") or []
            definition = "; ".join(str(gloss).strip() for gloss in glosses if str(gloss).strip())
            synonyms: dict[str, tuple[str, list[str]]] = {}
            for relation in sense["relations"]:
                if relation["type"] == "synonyms":
                    key = relation["target"].casefold()
                    if key not in synonyms:
                        synonyms[key] = (relation["target"], [])
                    synonyms[key][1].append(relation["evidence_id"])
            meanings.append({
                "pos": entry["part_of_speech"],
                "definition": definition,
                "source_sense_ids": [sense["sense_id"]],
                "labels": list(dict.fromkeys(sense.get("tags", []))),
                "synonyms": [
                    {"term": term, "evidence_ids": evidence_ids}
                    for term, evidence_ids in synonyms.values()
                ],
                "example_ids": [],
                "source_order": sense["source_order"],
                "source_entry_key": entry["entry_key"],
            })
    return meanings


def _select_initial_meanings(meanings: list[dict[str, Any]]) -> set[tuple[str, str]]:
    selected: set[tuple[str, str]] = set()
    pos_order = list(dict.fromkeys(meaning["pos"] for meaning in meanings))
    for pos in pos_order[:CORE_MEANING_LIMIT]:
        first = next(meaning for meaning in meanings if meaning["pos"] == pos)
        selected.add((first["source_entry_key"], first["source_sense_ids"][0]))
    for meaning in meanings:
        if len(selected) >= CORE_MEANING_LIMIT:
            break
        selected.add((meaning["source_entry_key"], meaning["source_sense_ids"][0]))
    return selected


def _deterministic_facts(evidence: dict[str, Any]) -> dict[str, Any]:
    forms = []
    pronunciations = []
    base_links = []
    etymologies = []
    for entry in evidence["entries"]:
        for form in entry.get("forms", []):
            forms.append({"entry_key": entry["entry_key"], "form": form})
        for sound in entry.get("sounds", []):
            tags = sound.get("tags", [])
            if sound.get("ipa") and US_PRONUNCIATION_TAGS.intersection(tags):
                pronunciations.append({
                    "entry_key": entry["entry_key"],
                    "ipa": sound["ipa"],
                    "tags": tags,
                })
        etymology = entry["etymology"]
        if etymology.get("text") or etymology.get("templates"):
            etymologies.append({
                "entry_key": entry["entry_key"],
                "etymology_number": entry.get("etymology_number"),
                "text": etymology.get("text"),
                "templates": etymology.get("templates", []),
                "dataset_version": entry["dataset_version"],
                "source_locator": entry["source_locator"],
            })
        for sense in entry["senses"]:
            for relation_type in ("form_of", "alt_of"):
                for relation in sense.get(relation_type, []):
                    if isinstance(relation, dict) and relation.get("word"):
                        base_links.append({
                            "source_sense_id": sense["sense_id"],
                            "word": relation["word"],
                            "type": relation_type,
                        })
    return {
        "forms": forms,
        "us_pronunciations": pronunciations,
        "base_links": base_links,
        "etymology_evidence": etymologies,
    }


def build_lexical_candidate(result: dict[str, Any]) -> dict[str, Any]:
    evidence = _project_source_evidence(result)
    if not evidence["entries"] or not any(entry["senses"] for entry in evidence["entries"]):
        raise ValueError(f"No source meanings are available for {result.get('word', '')!r}")
    meanings = _source_meanings(evidence)
    selected = _select_initial_meanings(meanings)
    by_pos: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for meaning in meanings:
        section = by_pos.setdefault(
            meaning["pos"], {"core_meanings": [], "additional_meanings": []}
        )
        bucket = (
            "core_meanings"
            if (meaning["source_entry_key"], meaning["source_sense_ids"][0]) in selected
            else "additional_meanings"
        )
        section[bucket].append({
            key: value for key, value in meaning.items()
            if key not in {"source_order", "source_entry_key"}
        })
    content = {
        "pos_sections": [
            {"pos": pos, **section} for pos, section in by_pos.items()
        ],
        "coverage": {
            "source_sense_ids": [
                sense["sense_id"]
                for entry in evidence["entries"]
                for sense in entry["senses"]
            ],
        },
    }
    facts = _deterministic_facts(evidence)
    candidate = {
        "schema_version": "deterministic-lexical-candidate-v1",
        "normalized_lemma": evidence["normalized_lemma"],
        "evidence_set_hash": evidence_set_hash(evidence),
        "wiktionary_versions": evidence["wiktionary_versions"],
        "validation_status": "source-derived",
        "content": content,
        "deterministic": facts,
        "etymology": facts["etymology_evidence"],
        "evidence_snapshot": evidence,
    }
    return candidate


def _dataset_date(version: str) -> date | None:
    match = re.search(r"(\d{4})(\d{2})(\d{2})$", version)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _newer_dataset_is_installed(
    saved: dict[str, Any], current: dict[str, Any] | str
) -> bool:
    saved_versions = saved.get("wiktionary_versions") or []
    current_versions = (
        current.get("wiktionary_versions") or []
        if isinstance(current, dict)
        else [current]
    )
    if len(current_versions) != 1 or len(saved_versions) != 1:
        return False
    saved_date = _dataset_date(saved_versions[0])
    current_date = _dataset_date(current_versions[0])
    return bool(saved_date and current_date and current_date > saved_date)


def reconcile_saved_state(
    state: LexicalState | None, query: str, persistence: Any
) -> LexicalState | None:
    """Resolve accepted database authority without refreshing saved snapshots."""
    normalized = query.strip().casefold()
    saved = persistence.load_active_version(normalized)
    matching_candidate = (
        state is not None
        and state.failure is None
        and state.candidate is not None
        and state.query.strip().casefold() == normalized
        and state.candidate.get("normalized_lemma", "").strip().casefold() == normalized
    )
    if not saved:
        if matching_candidate and state.origin in ("search", "refresh"):
            return LexicalState(normalized, candidate=state.candidate, origin=state.origin)
        return None
    if (
        matching_candidate
        and state.origin == "refresh"
        and state.saved_version
        and state.candidate.get("evidence_snapshot") is not None
        and evidence_set_hash(state.candidate["evidence_snapshot"])
        == state.candidate.get("evidence_set_hash")
    ):
        identity_fields = (
            "lexical_entry_id", "lexical_entry_version_id", "active_version_id",
            "candidate_identity", "evidence_set_hash",
        )
        same_saved_base = (
            state.saved_version.get("normalized_lemma") == saved.get("normalized_lemma") == normalized
            and all(
                state.saved_version.get(key) is not None
                and state.saved_version.get(key) == saved.get(key)
                for key in identity_fields
            )
            and state.saved_version.get("lexical_entry_version_id")
            == state.saved_version.get("active_version_id")
        )
        if (
            same_saved_base
            and state.candidate.get("evidence_set_hash") != saved.get("evidence_set_hash")
            and _newer_dataset_is_installed(
                saved.get("evidence_snapshot", {}),
                state.candidate["evidence_snapshot"],
            )
        ):
            return LexicalState(
                normalized,
                candidate=state.candidate,
                saved_version=saved,
                origin="refresh",
            )
    return LexicalState(
        normalized,
        candidate=saved["candidate_snapshot"],
        saved_version=saved,
        origin="saved",
    )


class LexicalWorkflow:
    def __init__(self, lexical_data_root: str, persistence: Any):
        self.lexical_data_root = lexical_data_root
        self.persistence = persistence

    def _current_database_path(self) -> str:
        root = Path(self.lexical_data_root)
        if root.is_dir():
            return str(resolve_active_database(root))
        return str(root)

    def _current_candidate(self, word: str) -> dict[str, Any]:
        return build_lexical_candidate(
            lookup(self._current_database_path(), word, include_wordnet=False)
        )

    def reconcile_authoritative_state(
        self, word: str, current: LexicalState | None = None
    ) -> LexicalState:
        normalized = word.strip().casefold()
        resolved = reconcile_saved_state(current, normalized, self.persistence)
        if resolved is not None:
            if resolved.origin == "saved":
                try:
                    root = Path(self.lexical_data_root)
                    if root.is_dir():
                        current_version = active_dataset_status(root)["dataset_version"]
                        if _newer_dataset_is_installed(
                            resolved.candidate.get("evidence_snapshot", {}),
                            current_version,
                        ):
                            current = lookup(
                                self._current_database_path(),
                                normalized,
                                include_wordnet=False,
                            )
                            resolved.refresh_available = any(
                                entry.get("senses") for entry in current.get("entries", [])
                            )
                    else:
                        current_candidate = self._current_candidate(normalized)
                        resolved.refresh_available = _newer_dataset_is_installed(
                            resolved.candidate.get("evidence_snapshot", {}),
                            current_candidate.get("evidence_snapshot", {}),
                        )
                except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as error:
                    resolved.dataset_status_error = str(error)
            return resolved
        return LexicalState(
            normalized,
            candidate=self._current_candidate(normalized),
            origin="search",
        )

    def search(self, word: str) -> LexicalState:
        return self.reconcile_authoritative_state(word)

    def save(self, state: LexicalState) -> dict[str, Any]:
        if not state.candidate or state.failure:
            raise ValueError("Only a source-derived candidate can be saved")
        saved = self.persistence.save_accepted_version(state.candidate, state.origin)
        if not saved or not saved.get("lexical_entry_version_id"):
            raise ValueError("Save verification failed before durable commit")
        return saved

    def flag(self, state: LexicalState) -> bool:
        if not state.candidate or state.failure:
            raise ValueError("Only a source-derived candidate can be flagged")
        return self.persistence.flag_candidate(state.candidate, state.origin)

    def refresh(self, state: LexicalState) -> LexicalState:
        if not state.saved_version or not state.refresh_available:
            raise ValueError("Refresh is unavailable for this saved entry")
        return LexicalState(
            state.query,
            candidate=self._current_candidate(state.query),
            saved_version=state.saved_version,
            origin="refresh",
        )


def source_detail_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in candidate.get("evidence_snapshot", {}).get("entries", []):
        for sense in entry.get("senses", []):
            rows.append({
                "pos": entry.get("part_of_speech", ""),
                "glosses": [str(gloss) for gloss in sense.get("glosses", [])],
                "labels": [str(label) for label in sense.get("tags", [])],
                "topics": [str(topic) for topic in sense.get("topics", [])],
                "examples": [
                    example.get("text", "") if isinstance(example, dict) else str(example)
                    for example in sense.get("examples", [])
                ],
                "sense_id": sense.get("sense_id"),
                "source_locator": entry.get("source_locator"),
                "dataset_version": entry.get("dataset_version"),
                "importer_version": entry.get("importer_version"),
                "source_record_hash": entry.get("source_record_hash"),
                "relations": [
                    {
                        "type": relation.get("type", ""),
                        "target": str(relation.get("target", "")),
                        "evidence_id": relation.get("evidence_id"),
                        "source_locator": relation.get("source_locator"),
                    }
                    for relation in sense.get("relations", [])
                ],
            })
    return rows


def meaning_source_rows(
    candidate: dict[str, Any], meaning: dict[str, Any], pos: str
) -> list[dict[str, Any]]:
    source_ids = list(dict.fromkeys(meaning.get("source_sense_ids", [])))
    rows = source_detail_rows(candidate)
    selected = []
    for sense_id in source_ids:
        matches = [row for row in rows if row["sense_id"] == sense_id]
        if len(matches) != 1 or matches[0]["pos"] != pos:
            raise ValueError(
                f"Meaning provenance cannot resolve source sense {sense_id} for {pos}"
            )
        selected.append(matches[0])
    return selected


def candidate_provenance(state: LexicalState) -> dict[str, Any]:
    candidate = state.candidate or {}
    evidence = candidate.get("evidence_snapshot", {})
    saved = state.saved_version or {}
    return {
        "Viewing": "Saved accepted version" if state.origin == "saved" else "Unsaved source-derived candidate",
        "Accepted version number": saved.get("version_number"),
        "Source datasets": ", ".join(evidence.get("wiktionary_versions", [])),
        "Evidence hash": candidate.get("evidence_set_hash"),
    }


def deduplicated_forms(candidate: dict[str, Any]) -> list[str]:
    forms = []
    seen = set()
    for item in candidate.get("deterministic", {}).get("forms", []):
        form_value = item.get("form", "")
        form = form_value.get("form", "") if isinstance(form_value, dict) else str(form_value)
        key = form.casefold()
        if form and key not in seen:
            seen.add(key)
            forms.append(form)
    return forms


POS_PRESENTATION_ORDER = {
    "noun": 10, "verb": 20, "adj": 30, "adjective": 30, "adv": 40,
    "adverb": 40, "pron": 50, "pronoun": 50, "prep": 60,
    "preposition": 60, "conj": 70, "conjunction": 70,
    "interj": 80, "interjection": 80, "name": 900, "symbol": 910,
}


def sort_pos_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        sections,
        key=lambda section: (
            POS_PRESENTATION_ORDER.get(section.get("pos", ""), 500),
            section.get("pos", ""),
        ),
    )
