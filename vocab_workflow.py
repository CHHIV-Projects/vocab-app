"""Framework-independent M004.5 lexical lifecycle controller."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vocab_lexical_engine import evidence_set_hash, lookup
from vocab_synthesis import SynthesisRuntime, project_synthesis_evidence, synthesize_word
from vocab_synthesis import strict_json_object, response_content, SynthesisFailure


@dataclass
class LexicalState:
    query: str
    candidate: dict[str, Any] | None = None
    saved_version: dict[str, Any] | None = None
    origin: str = "search"
    refresh_available: bool = False
    failure: dict[str, Any] | None = None

    @property
    def actions(self) -> dict[str, bool]:
        valid = self.candidate is not None and self.failure is None
        saved = self.saved_version is not None and self.origin == "saved"
        return {
            "save": valid and not saved,
            "retry": valid and saved,
            "refresh": valid and saved and self.refresh_available,
            "flag": valid,
        }


def reconcile_saved_state(state: LexicalState | None, query: str, persistence: Any) -> LexicalState | None:
    """Only authoritative PostgreSQL state may mark a word as saved."""
    normalized = query.strip().casefold()
    saved = persistence.load_active_version(normalized)
    if not saved:
        if state is not None and state.origin == "saved":
            return LexicalState(normalized, candidate=state.candidate, saved_version=None, origin="search")
        return None
    return LexicalState(
        normalized,
        candidate=saved.get("candidate_snapshot") or (state.candidate if state else None),
        saved_version=saved,
        origin="saved",
    )


class LexicalWorkflow:
    def __init__(self, database_path: str, persistence: Any, provider: Any, runtime: SynthesisRuntime | None = None):
        self.database_path = database_path
        self.persistence = persistence
        self.provider = provider
        self.runtime = runtime or SynthesisRuntime()

    def reconcile_authoritative_state(self, word: str, current: LexicalState | None = None) -> LexicalState:
        normalized = word.strip().casefold()
        saved = self.persistence.load_active_version(normalized)
        if saved:
            evidence = saved["evidence_snapshot"]
            current_lookup = lookup(self.database_path, normalized)
            current_hash = evidence_set_hash(project_synthesis_evidence(current_lookup)) if current_lookup.get("entries") else None
            return LexicalState(normalized, candidate=saved["candidate_snapshot"], saved_version=saved, origin="saved", refresh_available=current_hash is not None and current_hash != saved["evidence_set_hash"])

        if current and current.origin == "saved":
            candidate = current.candidate or self.search(normalized).candidate
            return LexicalState(normalized, candidate=candidate, saved_version=None, origin="search")

        result = synthesize_word(self.database_path, normalized, self.provider, self.runtime)
        candidate = enrich_candidate(result["result"], self.provider)
        return LexicalState(normalized, candidate=candidate, origin="search")

    def search(self, word: str) -> LexicalState:
        return self.reconcile_authoritative_state(word)

    def save(self, state: LexicalState) -> dict[str, Any]:
        if not state.candidate or state.failure:
            raise ValueError("Only a validated candidate can be saved")
        saved = self.persistence.save_accepted_version(state.candidate, state.origin)
        if not saved or not saved.get("lexical_entry_version_id"):
            raise ValueError("Save verification failed before durable commit")
        return saved

    def flag(self, state: LexicalState) -> bool:
        if not state.candidate or state.failure:
            raise ValueError("Only a valid candidate can be flagged")
        return self.persistence.flag_candidate(state.candidate, state.origin)

    def retry_saved(self, state: LexicalState) -> LexicalState:
        if not state.saved_version:
            raise ValueError("Retry requires an accepted saved version")
        evidence = state.saved_version["evidence_snapshot"]
        expected_hash = state.saved_version["evidence_set_hash"]
        if evidence_set_hash(evidence) != expected_hash:
            raise SynthesisFailure("saved_evidence_hash_mismatch", "Saved evidence snapshot failed integrity verification")
        result = synthesize_word(self.database_path, state.query, self.provider, self.runtime, retry=True, evidence_snapshot=evidence)
        return LexicalState(state.query, candidate=enrich_candidate(result["result"], self.provider), saved_version=state.saved_version, origin="retry")

    def refresh(self, state: LexicalState) -> LexicalState:
        if not state.saved_version or not state.refresh_available:
            raise ValueError("Refresh is unavailable for this saved entry")
        current = lookup(self.database_path, state.query)
        if not current.get("entries"):
            raise ValueError("Current canonical evidence is unavailable")
        evidence = project_synthesis_evidence(current)
        result = synthesize_word(self.database_path, state.query, self.provider, self.runtime, retry=True, evidence_snapshot=evidence)
        return LexicalState(state.query, candidate=enrich_candidate(result["result"], self.provider), saved_version=state.saved_version, origin="refresh")


def enrich_candidate(candidate: dict[str, Any], provider: Any) -> dict[str, Any]:
    """Attach deterministic Wiktionary synonyms and an evidence-bound etymology summary."""
    evidence = candidate.get("evidence_snapshot", {})
    sense_relations = {
        sense["sense_id"]: sense.get("relations", [])
        for entry in evidence.get("entries", [])
        for sense in entry.get("senses", [])
    }
    for section in candidate.get("content", {}).get("pos_sections", []):
        for meaning in section.get("core_meanings", []) + section.get("additional_meanings", []):
            terms: dict[str, list[str]] = {}
            for sense_id in meaning.get("source_sense_ids", []):
                for relation in sense_relations.get(sense_id, []):
                    if relation.get("type") != "synonyms":
                        continue
                    key = relation["target"].casefold()
                    terms.setdefault(key, []).append(relation["evidence_id"])
            meaning["synonyms"] = [{"term": key, "evidence_ids": ids} for key, ids in list(terms.items())[:5]]
    etymology = [entry["etymology"] for entry in evidence.get("entries", []) if entry.get("etymology", {}).get("text") or entry.get("etymology", {}).get("templates")]
    if etymology:
        prompt = {"task": "Summarize only the supplied etymology evidence for a learner. Preserve uncertainty and competing derivations. Return exactly one JSON object.", "evidence": etymology}
        schema = {"type": "object", "additionalProperties": False, "properties": {"summary": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["summary", "evidence_ids"]}
        response = provider.generate(json.dumps(prompt, ensure_ascii=False), seed=None, schema=schema)
        if response.get("done_reason") == "length":
            raise SynthesisFailure("etymology_output_truncated", "Etymology synthesis was truncated")
        summary = strict_json_object(response_content(response))
        valid_ids = {item["evidence_id"] for item in etymology}
        if not summary.get("summary") or not set(summary.get("evidence_ids", [])) <= valid_ids or not summary.get("evidence_ids"):
            raise SynthesisFailure("etymology_validation_failed", "Etymology summary lacked valid evidence references")
        candidate["etymology"] = summary
    return candidate


def source_detail_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize canonical evidence into safe learner-facing source-detail rows."""
    rows = []
    for entry in candidate.get("evidence_snapshot", {}).get("entries", []):
        for sense in entry.get("senses", []):
            rows.append({
                "pos": entry.get("part_of_speech", ""),
                "glosses": [str(gloss) for gloss in sense.get("glosses", [])],
                "labels": [str(label) for label in sense.get("tags", [])],
                "examples": [
                    example.get("text", "") if isinstance(example, dict) else str(example)
                    for example in sense.get("examples", [])
                ],
                "sense_id": sense.get("sense_id"),
                "relations": [
                    {"type": relation.get("type", ""), "target": str(relation.get("target", ""))}
                    for relation in sense.get("relations", [])
                ],
            })
    return rows


def deduplicated_forms(candidate: dict[str, Any]) -> list[str]:
    forms = []
    seen = set()
    for item in candidate.get("deterministic", {}).get("forms", []):
        form = item.get("form", {}).get("form", "") if isinstance(item.get("form"), dict) else str(item.get("form", ""))
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
    return sorted(sections, key=lambda section: (POS_PRESENTATION_ORDER.get(section.get("pos", ""), 500), section.get("pos", "")))
