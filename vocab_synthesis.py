"""Bounded GPT-OSS lexical synthesis over frozen canonical evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import requests

from vocab_lexical_engine import canonical_json, evidence_set_hash, lookup, wordnet_version


SYNTHESIS_SCHEMA_VERSION = "synthesis-v6-semantic-core-selection"
PACKER_VERSION = "packer-v1"
VALIDATOR_VERSION = "validator-v1"
POLICY_VERSION = "policy-v4-semantic-core-selection"
PROMPT_VERSION = "prompt-v4-semantic-core-selection"
DEFAULT_CONTEXT_TOKENS = 16384
DEFAULT_TARGET_INPUT_TOKENS = 5000
DEFAULT_OUTPUT_TOKENS = 3200
DEFAULT_HEADROOM_TOKENS = 1200
APPROVED_US_TAGS = frozenset({"US", "General-American"})


class ModelProvider(Protocol):
    def generate(self, prompt: str, *, seed: int | None = None, schema: dict[str, Any] | None = None) -> dict[str, Any]: ...


class SynthesisFailure(Exception):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _json_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _evidence_id(entry_key: str, field: str, value: Any) -> str:
    return f"WIK-EVID:{entry_key}:{field}:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _source_evidence(record: dict[str, Any], entry_key: str, normalized_sense: dict[str, Any]) -> dict[str, Any]:
    for source_order, sense in enumerate(record.get("senses", []), start=1):
        if source_order != normalized_sense["source_order"]:
            continue
        sense_id = normalized_sense["sense_id"]
        relations = []
        source = sense
        for relation_type in ("synonyms", "antonyms", "related", "derived", "hypernyms", "hyponyms"):
            for relation in source.get(relation_type, []):
                target = relation.get("word") if isinstance(relation, dict) else relation
                if target:
                    relations.append({
                        "evidence_id": _evidence_id(sense_id, relation_type, relation),
                        "type": relation_type,
                        "target": target,
                    })
        return {
            "sense_id": sense_id,
            "source_order": normalized_sense["source_order"],
            "glosses": sense.get("glosses", []),
            "raw_glosses": sense.get("raw_glosses", []),
            "tags": sense.get("tags", []),
            "topics": sense.get("topics", []),
            "examples": [
                {"evidence_id": _evidence_id(sense_id, "example", example), "text": example}
                for example in sense.get("examples", [])
            ],
            "relations": relations,
            "form_of": source.get("form_of", []),
            "alt_of": source.get("alt_of", []),
        }
    return {}


def project_synthesis_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Create a bounded, source-complete projection without raw record payloads."""
    entries = []
    for entry in result.get("entries", []):
        source = json.loads(entry["source_record_json"])
        senses = [_source_evidence(source, entry["entry_key"], sense) for sense in entry.get("senses", [])]
        entries.append({
            "entry_key": entry["entry_key"],
            "word": entry["word"],
            "part_of_speech": entry["part_of_speech"],
            "dataset_version": entry["dataset_version"],
            "importer_version": entry["importer_version"],
            "source_locator": entry["source_locator"],
            "source_record_hash": entry["source_record_hash"],
            "etymology": {
                "text": source.get("etymology_text"),
                "templates": source.get("etymology_templates", []),
                "evidence_id": _evidence_id(entry["entry_key"], "etymology", source.get("etymology_templates", [])),
            },
            "forms": source.get("forms", []),
            "pronunciations": source.get("sounds", []),
            "senses": senses,
        })
    versions = sorted({entry["dataset_version"] for entry in entries})
    return {
        "schema_version": "synthesis-evidence-v1",
        "normalized_lemma": result.get("word", "").casefold(),
        "wiktionary_versions": versions,
        "wordnet_version": _safe_wordnet_version() if result.get("wordnet") else None,
        "entries": entries,
        "wordnet": sorted(result.get("wordnet", []), key=lambda item: item.get("synset_id", "")),
    }


def _safe_wordnet_version() -> str | None:
    try:
        return wordnet_version()
    except (LookupError, ModuleNotFoundError):
        return None


def _sense_groups(evidence: dict[str, Any]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for entry in evidence["entries"]:
        group = []
        for sense in entry["senses"]:
            group.append({"entry_key": entry["entry_key"], "part_of_speech": entry["part_of_speech"], **sense})
        if group:
            groups.append(group)
    return groups


def estimate_tokens(value: Any) -> int:
    return max(1, (len(canonical_json(value).encode("utf-8")) + 3) // 4)


def pack_evidence(evidence: dict[str, Any], *, target_tokens: int = DEFAULT_TARGET_INPUT_TOKENS) -> list[dict[str, Any]]:
    """Chunk complete source senses in entry/POS/source order; never filter senses."""
    packages: list[dict[str, Any]] = []
    package_senses: list[dict[str, Any]] = []
    for group_index, group in enumerate(_sense_groups(evidence)):
        if package_senses and estimate_tokens(package_senses + group) > target_tokens:
            packages.append({"chunk_id": f"chunk-{len(packages) + 1}", "senses": package_senses})
            package_senses = []
        current: list[dict[str, Any]] = []
        for sense in group:
            candidate = current + [sense]
            if current and estimate_tokens(candidate) > target_tokens:
                package_senses.extend(current)
                packages.append({"chunk_id": f"chunk-{len(packages) + 1}", "senses": package_senses})
                package_senses = []
                current = [sense]
            else:
                current = candidate
        if current:
            package_senses.extend(current)
    if package_senses:
        packages.append({"chunk_id": f"chunk-{len(packages) + 1}", "senses": package_senses})
    if not packages:
        packages.append({"chunk_id": "chunk-1", "senses": []})
    for package in packages:
        package["estimated_input_tokens"] = estimate_tokens(package)
    return packages


def strict_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text.startswith("{") or not text.endswith("}"):
        raise SynthesisFailure("parse_not_exact_object", "Model output was not exactly one JSON object")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise SynthesisFailure("parse_invalid_json", str(error)) from error
    if not isinstance(value, dict):
        raise SynthesisFailure("parse_not_object", "Model output JSON was not an object")
    return value


class OllamaProvider:
    def __init__(self, endpoint: str | None = None, model: str = "gpt-oss:20b", timeout: float = 180):
        self.endpoint = (endpoint or os.environ.get("VOCAB_OLLAMA_URL", "http://ollama:11434")).rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, *, seed: int | None = None, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": 0, "num_predict": DEFAULT_OUTPUT_TOKENS, "num_ctx": DEFAULT_CONTEXT_TOKENS}
        if seed is not None:
            options["seed"] = seed
        response = requests.post(self.endpoint + "/api/chat", json={
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema or lexical_content_schema(),
            "think": "low",
            "keep_alive": "5m",
            "options": options,
        }, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def lexical_content_schema(evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    meaning_properties = {
        "definition": {"type": "string"},
        "source_sense_ids": {"type": "array", "items": {"type": "string"}},
        "labels": {"type": "array", "items": {"type": "string"}},
        "synonyms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"term": {"type": "string"}, "evidence_id": {"type": "string"}},
                "required": ["term", "evidence_id"],
            },
        },
        "example_ids": {"type": "array", "items": {"type": "string"}},
    }
    meaning = {
        "type": "object",
        "additionalProperties": False,
        "properties": meaning_properties,
        "required": list(meaning_properties),
    }
    section_properties = {
        "pos": {"type": "string"},
        "core_meanings": {"type": "array", "items": meaning},
        "additional_meanings": {"type": "array", "items": meaning},
    }
    section = {
        "type": "object",
        "additionalProperties": False,
        "properties": section_properties,
        "required": list(section_properties),
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "pos_sections": {"type": "array", "items": section},
            "coverage": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"source_sense_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["source_sense_ids"],
            },
        },
        "required": ["pos_sections", "coverage"],
    }
    if evidence is not None:
        sense_ids = [sense["sense_id"] for entry in evidence["entries"] for sense in entry["senses"]]
        example_ids = [example["evidence_id"] for entry in evidence["entries"] for sense in entry["senses"] for example in sense.get("examples", [])]
        relation_ids = [relation["evidence_id"] for entry in evidence["entries"] for sense in entry["senses"] for relation in sense.get("relations", [])]
        labels = sorted({label for entry in evidence["entries"] for sense in entry["senses"] for label in sense.get("tags", [])})
        meaning_properties = schema["properties"]["pos_sections"]["items"]["properties"]["core_meanings"]["items"]["properties"]
        additional_properties = schema["properties"]["pos_sections"]["items"]["properties"]["additional_meanings"]["items"]["properties"]
        for properties in (meaning_properties, additional_properties):
            properties["source_sense_ids"]["items"]["enum"] = sense_ids
            properties["example_ids"]["items"]["enum"] = example_ids
            properties["labels"]["items"]["enum"] = labels
            properties["synonyms"]["items"]["properties"]["evidence_id"]["enum"] = relation_ids
        schema["properties"]["coverage"]["properties"]["source_sense_ids"]["items"]["enum"] = sense_ids
    return schema


def sense_aliases(package: dict[str, Any]) -> dict[str, str]:
    return {f"S{index:03d}": sense["sense_id"] for index, sense in enumerate(package["senses"], start=1)}


def scaffold_schema(package: dict[str, Any]) -> dict[str, Any]:
    result_properties = {
        "definition": {"type": "string"},
    }
    result = {
        "type": "object",
        "additionalProperties": False,
        "properties": result_properties,
        "required": ["definition"],
    }
    aliases = list(sense_aliases(package))
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sense_results": {
                "type": "object",
                "additionalProperties": False,
                "properties": {alias: result for alias in aliases},
                "required": aliases,
            },
        },
        "required": ["sense_results"],
    }


def scaffold_prompt(package: dict[str, Any], evidence: dict[str, Any]) -> str:
    aliases = sense_aliases(package)
    source = []
    for alias, canonical_id in aliases.items():
        sense = next(item for item in package["senses"] if item["sense_id"] == canonical_id)
        source.append({"alias": alias, "pos": sense["part_of_speech"], "sense": sense})
    return canonical_json({
        "task": "Return exactly one JSON object matching the supplied schema.",
        "authority": "Write one concise learner-friendly paraphrase for every required sense alias. Do not omit, merge, or invent a sense. Use only the supplied sense evidence. Do not output POS, IDs, labels, examples, or other factual fields.",
        "lemma": evidence["normalized_lemma"],
        "required_sense_aliases": list(aliases),
        "source_senses": source,
    })


def validate_scaffold(value: dict[str, Any], package: dict[str, Any]) -> list[str]:
    aliases = sense_aliases(package)
    if set(value) != {"sense_results"} or not isinstance(value.get("sense_results"), dict):
        return ["scaffold_structure"]
    if set(value["sense_results"]) != set(aliases):
        return ["scaffold_alias_coverage"]
    errors = []
    for alias in aliases:
        result = value["sense_results"][alias]
        if not isinstance(result, dict) or set(result) != {"definition"} or not isinstance(result.get("definition"), str) or not result["definition"].strip():
            errors.append(f"scaffold_result:{alias}")
    return errors


def scaffold_to_content(value: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    aliases = sense_aliases(package)
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for alias, canonical_id in aliases.items():
        sense = next(item for item in package["senses"] if item["sense_id"] == canonical_id)
        by_pos.setdefault(sense["part_of_speech"], []).append({
            "definition": value["sense_results"][alias]["definition"],
            "source_sense_ids": [canonical_id],
            "labels": sense.get("tags", []),
            "synonyms": [],
            "example_ids": [],
        })
    sections = []
    for pos, meanings in by_pos.items():
        core_count = min(5, len(meanings))
        sections.append({"pos": pos, "core_meanings": meanings[:core_count], "additional_meanings": meanings[core_count:]})
    return {"pos_sections": sections, "coverage": {"source_sense_ids": list(aliases.values())}}


def deterministic_group_assignments(package: dict[str, Any]) -> dict[str, str]:
    """Provide an exhaustive baseline grouping; semantic consolidation remains a later stage."""
    return {alias: f"G{index:03d}" for index, alias in enumerate(sense_aliases(package), start=1)}


MATERIAL_LABELS = frozenset({
    "archaic", "dated", "figurative", "formal", "humorous", "informal",
    "literary", "obsolete", "offensive", "rare", "regional", "slang",
    "technical", "vulgar",
})


def grouping_schema(aliases: list[str], group_ids: list[str]) -> dict[str, Any]:
    definition = {"type": "string"}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "group_assignments": {"type": "object", "additionalProperties": False, "properties": {alias: {"type": "string", "enum": group_ids} for alias in aliases}, "required": aliases},
            "group_definitions": {"type": "object", "additionalProperties": False, "properties": {group: definition for group in group_ids}, "required": group_ids},
        },
        "required": ["group_assignments", "group_definitions"],
    }


def core_selection_schema(group_ids: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": {"core_group_ids": {"type": "array", "uniqueItems": True, "maxItems": 5, "items": {"type": "string", "enum": group_ids}}}, "required": ["core_group_ids"]}


def grouping_prompt(pos: str, senses: list[dict[str, Any]], aliases: dict[str, str]) -> str:
    return canonical_json({
        "task": "Return exactly one JSON object with exactly two keys: group_assignments and group_definitions. Group only sufficiently overlapping learner meanings within this one POS. Keep materially distinct senses separate. Never merge senses with different material labels such as archaic, dated, figurative, formal, humorous, informal, literary, obsolete, offensive, rare, regional, slang, technical, or vulgar. Return a nonempty definition string for every used group and an empty string for every unused allowed group ID. Do not invent facts.",
        "pos": pos,
        "required_aliases": list(aliases),
        "allowed_group_ids": [f"G{index:03d}" for index in range(1, len(aliases) + 1)],
        "sense_paraphrases": [{"alias": alias, "definition": sense["definition"], "source_labels": sense.get("labels", [])} for alias, sense in zip(aliases, senses)],
    })


def validate_grouping(value: dict[str, Any], aliases: dict[str, str], senses: list[dict[str, Any]]) -> list[str]:
    allowed_aliases = set(aliases)
    allowed_groups = {f"G{index:03d}" for index in range(1, len(aliases) + 1)}
    errors = []
    assignments = value.get("group_assignments") if isinstance(value, dict) else None
    definitions = value.get("group_definitions") if isinstance(value, dict) else None
    if set(value) != {"group_assignments", "group_definitions"} or not isinstance(assignments, dict) or not isinstance(definitions, dict):
        return ["grouping_structure"]
    if set(assignments) != allowed_aliases:
        errors.append("group_alias_coverage")
    groups = set(assignments.values())
    if not groups <= allowed_groups:
        errors.append("unknown_group_id")
    if set(definitions) != allowed_groups:
        errors.append("group_definition_coverage")
    if not all(isinstance(definitions.get(group), str) for group in allowed_groups):
        errors.append("group_definition_structure")
    if any(not definitions.get(group, "").strip() for group in groups):
        errors.append("missing_used_group_definition")
    labels_by_alias = {alias: set(sense.get("labels", [])) & MATERIAL_LABELS for alias, sense in zip(aliases, senses)}
    for group in groups:
        members = [alias for alias, assigned in assignments.items() if assigned == group]
        material = {tuple(sorted(labels_by_alias[alias])) for alias in members}
        if len(material) > 1:
            errors.append(f"material_label_boundary:{group}")
    return sorted(set(errors))


def grouped_content(group_results: list[tuple[str, dict[str, Any], dict[str, str], list[dict[str, Any]]]], evidence: dict[str, Any]) -> dict[str, Any]:
    meanings_by_pos: dict[str, list[dict[str, Any]]] = {}
    all_coverage = []
    for pos, result, aliases, senses in group_results:
        members: dict[str, list[str]] = {}
        for alias, group in result["group_assignments"].items():
            members.setdefault(group, []).append(aliases[alias])
        meanings = []
        sense_by_id = {aliases[alias]: sense for alias, sense in zip(aliases, senses)}
        for group, source_ids in members.items():
            labels = sorted({label for source_id in source_ids for label in sense_by_id[source_id].get("labels", [])})
            meanings.append({"definition": result["group_definitions"][group], "source_sense_ids": source_ids, "labels": labels, "synonyms": [], "example_ids": []})
            all_coverage.extend(source_ids)
        core_ids = set(result.get("core_group_ids", []))
        for group, meaning in zip(members, meanings):
            meaning["_is_core"] = group in core_ids
        meanings_by_pos.setdefault(pos, []).extend(meanings)
    sections = []
    for pos, meanings in meanings_by_pos.items():
        core = []
        additional = []
        for meaning in meanings:
            (core if meaning.pop("_is_core", False) else additional).append(meaning)
        sections.append({"pos": pos, "core_meanings": core, "additional_meanings": additional})
    return {"pos_sections": sections, "coverage": {"source_sense_ids": all_coverage}}


def response_content(response: dict[str, Any]) -> str:
    message = response.get("message")
    if not isinstance(message, dict):
        raise SynthesisFailure("provider_response_shape", "Ollama chat response did not contain a message object")
    content = message.get("content")
    if not isinstance(content, str):
        raise SynthesisFailure("provider_response_shape", "Ollama chat message did not contain string content")
    return content


def response_metadata(response: dict[str, Any]) -> dict[str, Any]:
    message = response.get("message") if isinstance(response.get("message"), dict) else {}
    return {
        key: response.get(key)
        for key in ("done", "done_reason", "prompt_eval_count", "eval_count", "prompt_eval_duration", "eval_duration", "total_duration")
    } | {
        "message_content": message.get("content", "")[:65536],
        "message_thinking": message.get("thinking", "")[:65536],
        "message_content_truncated": len(message.get("content", "")) > 65536 if isinstance(message.get("content", ""), str) else False,
        "message_thinking_truncated": len(message.get("thinking", "")) > 65536 if isinstance(message.get("thinking", ""), str) else False,
    }


def _allowed_labels(evidence: dict[str, Any], sense_ids: set[str]) -> set[str]:
    return {
        tag
        for entry in evidence["entries"]
        for sense in entry["senses"]
        if sense["sense_id"] in sense_ids
        for tag in sense.get("tags", [])
    }


def _sense_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {sense["sense_id"]: {"pos": entry["part_of_speech"], **sense} for entry in evidence["entries"] for sense in entry["senses"]}


def validate_content(content: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(content) != {"pos_sections", "coverage"}:
        errors.append("content_fields")
        return errors
    if not isinstance(content.get("pos_sections"), list) or not isinstance(content.get("coverage"), dict):
        return ["content_types"]
    sense_map = _sense_map(evidence)
    supplied = set(sense_map)
    accounted: list[str] = []
    for section in content.get("pos_sections", []):
        if not isinstance(section, dict):
            errors.append("section_type")
            continue
        if set(section) != {"pos", "core_meanings", "additional_meanings"}:
            errors.append("unknown_section_fields")
        pos = section.get("pos")
        if pos not in {sense["pos"] for sense in sense_map.values()}:
            errors.append("unsupported_pos")
        for bucket in ("core_meanings", "additional_meanings"):
            if not isinstance(section.get(bucket), list):
                errors.append("meaning_bucket_type")
                continue
            for meaning in section.get(bucket, []):
                if not isinstance(meaning, dict):
                    errors.append("meaning_type")
                    continue
                if set(meaning) != {"definition", "source_sense_ids", "labels", "synonyms", "example_ids"}:
                    errors.append("unknown_meaning_fields")
                ids = meaning.get("source_sense_ids")
                if not isinstance(meaning.get("definition"), str) or not meaning["definition"].strip() or not isinstance(ids, list) or not ids:
                    errors.append("meaning_structure")
                    continue
                for sense_id in ids:
                    if sense_id not in sense_map:
                        errors.append("unknown_sense_id")
                    elif sense_map[sense_id]["pos"] != pos:
                        errors.append("cross_pos")
                    accounted.append(sense_id)
                allowed = _allowed_labels(evidence, set(ids) & supplied)
                if not isinstance(meaning.get("labels"), list) or not set(meaning.get("labels", [])) <= allowed:
                    errors.append("unsupported_label")
                valid_examples = {example["evidence_id"] for sense_id in set(ids) & supplied for example in sense_map[sense_id].get("examples", [])}
                if not isinstance(meaning.get("example_ids"), list) or not set(meaning.get("example_ids", [])) <= valid_examples:
                    errors.append("unsupported_example")
                valid_relations = {relation["evidence_id"]: relation["target"] for sense_id in set(ids) & supplied for relation in sense_map[sense_id].get("relations", [])}
                if not isinstance(meaning.get("synonyms"), list):
                    errors.append("synonym_type")
                    continue
                for synonym in meaning.get("synonyms", []):
                    if isinstance(synonym, dict) and set(synonym) != {"term", "evidence_id"}:
                        errors.append("unknown_synonym_fields")
                    if not isinstance(synonym, dict) or synonym.get("evidence_id") not in valid_relations or synonym.get("term") != valid_relations.get(synonym.get("evidence_id")):
                        errors.append("unsupported_synonym")
    if set(accounted) != supplied or len(accounted) != len(set(accounted)):
        errors.append("incomplete_or_duplicate_coverage")
    coverage_ids = content.get("coverage", {}).get("source_sense_ids")
    if not isinstance(coverage_ids, list) or set(coverage_ids) != supplied:
        errors.append("coverage_accounting")
    return sorted(set(errors))


def build_envelope(content: dict[str, Any], evidence: dict[str, Any], *, model: str, digest: str | None, seed: int | None, attempt_id: str) -> dict[str, Any]:
    return {
        "schema_version": SYNTHESIS_SCHEMA_VERSION,
        "normalized_lemma": evidence["normalized_lemma"],
        "evidence_set_hash": evidence_set_hash(evidence),
        "wiktionary_versions": evidence["wiktionary_versions"],
        "wordnet_version": evidence["wordnet_version"],
        "model": model,
        "model_digest": digest,
        "prompt_version": PROMPT_VERSION,
        "policy_version": POLICY_VERSION,
        "packer_version": PACKER_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "inference": {"temperature": 0, "think": "low", "seed": seed, "num_predict": DEFAULT_OUTPUT_TOKENS, "num_ctx": DEFAULT_CONTEXT_TOKENS},
        "attempt_id": attempt_id,
        "validation_status": "validated",
        "content": content,
    }


def deterministic_facts(evidence: dict[str, Any]) -> dict[str, Any]:
    """Assemble factual fields without spending model context or trusting model output."""
    forms = []
    pronunciations = []
    base_links = []
    etymology = []
    for entry in evidence["entries"]:
        for form in entry.get("forms", []):
            forms.append({"entry_key": entry["entry_key"], "form": form})
        for sound in entry.get("pronunciations", []):
            if sound.get("ipa") and APPROVED_US_TAGS.intersection(sound.get("tags", [])):
                pronunciations.append({"entry_key": entry["entry_key"], "ipa": sound["ipa"], "tags": sound.get("tags", [])})
        if entry.get("etymology", {}).get("text") or entry.get("etymology", {}).get("templates"):
            etymology.append(entry["etymology"])
        for sense in entry["senses"]:
            for relation in sense.get("form_of", []):
                if isinstance(relation, dict) and relation.get("word"):
                    base_links.append({"source_sense_id": sense["sense_id"], "word": relation["word"], "type": "form_of"})
    return {"forms": forms, "us_pronunciations": pronunciations, "base_links": base_links, "etymology_evidence": etymology}


def synthesis_prompt(package: dict[str, Any], evidence: dict[str, Any]) -> str:
    instructions = {
        "task": "Return exactly one JSON object matching the supplied machine-readable schema and no surrounding prose.",
        "authority": "Use only supplied evidence. Do not invent lexical facts, examples, labels, synonyms, forms, pronunciations, or relationships. Every supplied source sense must be represented by exactly one learner meaning, either core or additional. Every supplied source sense ID must occur exactly once in the output meaning references and exactly once in coverage. Do not put an evidence ID under a different sense. If a sense has no example evidence, use an empty example_ids array. Preserve POS boundaries.",
        "evidence": package,
        "required_source_sense_ids": [sense["sense_id"] for sense in package["senses"]],
        "lemma": evidence["normalized_lemma"],
    }
    return canonical_json(instructions)


def _subset_evidence(evidence: dict[str, Any], sense_ids: set[str]) -> dict[str, Any]:
    subset = dict(evidence)
    subset["entries"] = []
    for entry in evidence["entries"]:
        senses = [sense for sense in entry["senses"] if sense["sense_id"] in sense_ids]
        if senses:
            subset["entries"].append({**entry, "senses": senses})
    return subset


def _assemble_chunk_content(contents: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any]:
    meanings_by_pos: dict[str, list[dict[str, Any]]] = {}
    for content in contents:
        for section in content["pos_sections"]:
            meanings_by_pos.setdefault(section["pos"], []).extend(section["core_meanings"] + section["additional_meanings"])
    sections = []
    for pos, meanings in meanings_by_pos.items():
        core_count = min(5, len(meanings))
        sections.append({"pos": pos, "core_meanings": meanings[:core_count], "additional_meanings": meanings[core_count:]})
    return {"pos_sections": sections, "coverage": {"source_sense_ids": [sense["sense_id"] for entry in evidence["entries"] for sense in entry["senses"]]}}


def synthesize_word(
    database_path: str | Path,
    word: str,
    provider: ModelProvider,
    runtime: SynthesisRuntime,
    *,
    seed: int | None = None,
    target_tokens: int = DEFAULT_TARGET_INPUT_TOKENS,
    retry: bool = False,
) -> dict[str, Any]:
    result = lookup(database_path, word)
    evidence = project_synthesis_evidence(result)
    packages = pack_evidence(evidence, target_tokens=target_tokens)
    identity = {
        "normalized_lemma": evidence["normalized_lemma"],
        "evidence_set_hash": evidence_set_hash(evidence),
        "model": getattr(provider, "model", provider.__class__.__name__),
        "prompt_version": PROMPT_VERSION,
        "policy_version": POLICY_VERSION,
        "schema_version": SYNTHESIS_SCHEMA_VERSION,
        "packer_version": PACKER_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "provider_contract": "ollama-chat-v1",
        "target_input_tokens": target_tokens,
    }
    if not retry:
        cached = runtime.read_cache(identity)
        if cached:
            return {"status": "cached", "result": cached, "package_count": len(packages)}
    attempt_id = uuid.uuid4().hex
    response: dict[str, Any] | None = None
    try:
        contents = []
        stage_metadata = []
        for package in packages:
            package_ids = {sense["sense_id"] for sense in package["senses"]}
            stage_evidence = _subset_evidence(evidence, package_ids)
            response = provider.generate(scaffold_prompt(package, stage_evidence), seed=seed, schema=scaffold_schema(package))
            stage_metadata.append({"chunk_id": package["chunk_id"], "estimated_input_tokens": package["estimated_input_tokens"], "response": response_metadata(response)})
            if response.get("done_reason") == "length":
                raise SynthesisFailure("output_truncated", "Ollama ended generation at the output limit", details=response_metadata(response))
            scaffold = strict_json_object(response_content(response))
            scaffold_errors = validate_scaffold(scaffold, package)
            if scaffold_errors:
                raise SynthesisFailure("scaffold_validation_failed", "Model did not return every required sense alias", details={"chunk_id": package["chunk_id"], "errors": scaffold_errors})
            content = scaffold_to_content(scaffold, package)
            errors = validate_content(content, stage_evidence)
            if errors:
                raise SynthesisFailure("validation_failed", "Model content failed deterministic validation", details={"chunk_id": package["chunk_id"], "errors": errors})
            contents.append(content)
        per_pos: dict[str, list[dict[str, Any]]] = {}
        for content in contents:
            for section in content["pos_sections"]:
                per_pos.setdefault(section["pos"], []).extend(section["core_meanings"] + section["additional_meanings"])
        group_results = []
        for pos, meanings in per_pos.items():
            partitions: dict[tuple[str, ...], list[dict[str, Any]]] = {}
            for meaning in meanings:
                signature = tuple(sorted(set(meaning.get("labels", [])) & MATERIAL_LABELS))
                partitions.setdefault(signature, []).append(meaning)
            for partition_index, partition in enumerate(partitions.values(), start=1):
                aliases = {f"S{index:03d}": meaning["source_sense_ids"][0] for index, meaning in enumerate(partition, start=1)}
                group_schema = grouping_schema(list(aliases), [f"G{index:03d}" for index in range(1, len(aliases) + 1)])
                group_response = provider.generate(grouping_prompt(pos, partition, aliases), seed=seed, schema=group_schema)
                stage_metadata.append({"chunk_id": f"group-{pos}-{partition_index}", "estimated_input_tokens": estimate_tokens(partition), "response": response_metadata(group_response)})
                if group_response.get("done_reason") == "length":
                    raise SynthesisFailure("output_truncated", "Ollama ended grouping at the output limit", details=response_metadata(group_response))
                grouping = strict_json_object(response_content(group_response))
                grouping_errors = validate_grouping(grouping, aliases, partition)
                if grouping_errors:
                    raise SynthesisFailure("grouping_validation_failed", "Model grouping failed deterministic validation", details={"pos": pos, "errors": grouping_errors})
                group_results.append((pos, grouping, aliases, partition))
        final_group_results = []
        for pos in sorted(per_pos):
            partitions = [item for item in group_results if item[0] == pos]
            global_assignments = {}
            global_definitions = {}
            global_aliases = {}
            global_senses = []
            next_group = 1
            for _, grouping, aliases, senses in partitions:
                local_to_global = {}
                for local_group in sorted(set(grouping["group_assignments"].values())):
                    global_group = f"G{next_group:03d}"
                    next_group += 1
                    local_to_global[local_group] = global_group
                    global_definitions[global_group] = grouping["group_definitions"][local_group]
                for alias, canonical_id in aliases.items():
                    global_alias = f"S{len(global_aliases) + 1:03d}"
                    global_aliases[global_alias] = canonical_id
                    global_assignments[global_alias] = local_to_global[grouping["group_assignments"][alias]]
                    global_senses.append(next(sense for sense in senses if sense["source_sense_ids"][0] == canonical_id))
            global_ids = sorted(global_definitions)
            core_response = provider.generate(
                canonical_json({"task": "Return exactly one JSON object with exactly one key: core_group_ids. Select up to five core learner groups for this POS. Prefer common, contemporary, materially distinct meanings, but do not invent frequency claims or discard groups.", "pos": pos, "groups": [{"group_id": group, "definition": global_definitions[group]} for group in global_ids]}),
                seed=seed,
                schema=core_selection_schema(global_ids),
            )
            stage_metadata.append({"chunk_id": f"core-{pos}", "estimated_input_tokens": estimate_tokens(global_definitions), "response": response_metadata(core_response)})
            if core_response.get("done_reason") == "length":
                raise SynthesisFailure("output_truncated", "Ollama ended core selection at the output limit", details=response_metadata(core_response))
            core_selection = strict_json_object(response_content(core_response))
            if set(core_selection) != {"core_group_ids"} or not isinstance(core_selection["core_group_ids"], list) or len(core_selection["core_group_ids"] ) != len(set(core_selection["core_group_ids"])) or not set(core_selection["core_group_ids"]) <= set(global_ids) or len(core_selection["core_group_ids"]) > 5:
                raise SynthesisFailure("core_selection_validation_failed", "Model core selection was not a valid subset of POS groups", details={"pos": pos})
            final_group_results.append((pos, {"group_assignments": global_assignments, "group_definitions": global_definitions, "core_group_ids": core_selection["core_group_ids"]}, global_aliases, global_senses))
        content = grouped_content(final_group_results, evidence)
        errors = validate_content(content, evidence)
        if errors:
            raise SynthesisFailure("validation_failed", "Assembled model content failed deterministic validation", details={"errors": errors})
        envelope = build_envelope(content, evidence, model=identity["model"], digest=response.get("model_digest"), seed=seed, attempt_id=attempt_id)
        envelope["deterministic"] = deterministic_facts(evidence)
        envelope["stages"] = stage_metadata
        envelope["package_count"] = len(packages)
        envelope["grouping"] = {
            "mode": "pos-local-semantic",
            "partitions": [{"pos": pos, "assignments": result["group_assignments"], "definitions": result["group_definitions"], "core_group_ids": result["core_group_ids"]} for pos, result, _, _ in final_group_results],
        }
        runtime.write_cache(identity, envelope)
        return {"status": "validated", "result": envelope, "package_count": len(packages)}
    except Exception as error:
        failure = error if isinstance(error, SynthesisFailure) else SynthesisFailure("provider_failure", str(error))
        details = dict(failure.details)
        if response:
            details["response_metadata"] = response_metadata(response)
        runtime.record_failure({"timestamp": time.time(), "attempt_id": attempt_id, "normalized_lemma": evidence["normalized_lemma"], "evidence_set_hash": evidence_set_hash(evidence), "identity": identity, "package_count": len(packages), "package_estimates": [{"chunk_id": package["chunk_id"], "estimated_input_tokens": package["estimated_input_tokens"]} for package in packages], "error_code": failure.code, "error": str(failure), "details": details})
        raise failure


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


class SynthesisRuntime:
    def __init__(self, runtime_root: str | Path = "/home/chuck/.local/share/vocab-app/runtime"):
        self.root = Path(runtime_root)
        self.cache = self.root / "synthesis-cache"
        self.diagnostics = self.root / "failure-diagnostics"

    def cache_path(self, identity: dict[str, Any]) -> Path:
        return self.cache / (hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest() + ".json")

    def read_cache(self, identity: dict[str, Any]) -> dict[str, Any] | None:
        path = self.cache_path(identity)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def write_cache(self, identity: dict[str, Any], value: dict[str, Any]) -> None:
        _atomic_write(self.cache_path(identity), value)
        self.cleanup()

    def record_failure(self, failure: dict[str, Any]) -> Path:
        path = self.diagnostics / (f"{int(time.time())}-{uuid.uuid4().hex}.json")
        _atomic_write(path, failure)
        self.cleanup()
        return path

    def cleanup(self, *, max_age_seconds: int = 30 * 24 * 60 * 60, max_files: int = 1000, max_bytes: int = 100 * 1024 * 1024) -> None:
        now = time.time()
        for directory in (self.cache, self.diagnostics):
            if not directory.is_dir():
                continue
            files = sorted((path for path in directory.glob("*.json") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
            retained: list[Path] = []
            total = 0
            for path in files:
                size = path.stat().st_size
                if now - path.stat().st_mtime > max_age_seconds or len(retained) >= max_files or total + size > max_bytes:
                    path.unlink(missing_ok=True)
                else:
                    retained.append(path)
                    total += size
