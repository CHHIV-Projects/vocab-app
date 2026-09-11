import unittest

from vocab_consolidation_orchestrator import (
    lexical_dataset_identity_from_evidence,
    partitions_from_synthesis_evidence,
)


def synthesis_style_evidence():
    """Shape mirroring real `vocab_synthesis.project_synthesis_evidence()` output: senses
    expose material/register information under `"tags"`, not `"labels"`."""
    return {
        "normalized_lemma": "bank",
        "wiktionary_versions": ["wiktionary-2024-01"],
        "wordnet_version": "wordnet-3.1",
        "entries": [{
            "entry_key": "bank",
            "part_of_speech": "noun",
            "senses": [
                {"sense_id": "bank-1", "source_order": 1, "glosses": ["a financial institution"], "tags": [], "topics": [], "examples": [], "relations": []},
                {"sense_id": "bank-2", "source_order": 2, "glosses": ["the land alongside a river"], "tags": [], "topics": [], "examples": [], "relations": []},
                {"sense_id": "bank-3", "source_order": 3, "glosses": ["an archaic term for a bench"], "tags": ["archaic"], "topics": [], "examples": [], "relations": []},
            ],
        }],
        "wordnet": [],
    }


class SynthesisEvidenceAdapterTests(unittest.TestCase):
    def test_material_partitions_respect_real_tags_field(self):
        partitions = partitions_from_synthesis_evidence(synthesis_style_evidence())
        signatures = {partition.material_partition for partition in partitions}
        self.assertIn((), signatures)
        self.assertIn(("archaic",), signatures)
        # The archaic sense must be isolated from the two non-material senses.
        archaic_partition = next(p for p in partitions if p.material_partition == ("archaic",))
        self.assertEqual({member["sense_id"] for member in archaic_partition.members}, {"bank-3"})
        plain_partition = next(p for p in partitions if p.material_partition == ())
        self.assertEqual({member["sense_id"] for member in plain_partition.members}, {"bank-1", "bank-2"})

    def test_adapter_preserves_original_tags_field(self):
        partitions = partitions_from_synthesis_evidence(synthesis_style_evidence())
        archaic_partition = next(p for p in partitions if p.material_partition == ("archaic",))
        member = archaic_partition.members[0]
        self.assertEqual(member["tags"], ["archaic"])
        self.assertEqual(member["labels"], ["archaic"])

    def test_adapter_does_not_mutate_caller_evidence(self):
        evidence = synthesis_style_evidence()
        original_sense = evidence["entries"][0]["senses"][0]
        partitions_from_synthesis_evidence(evidence)
        self.assertNotIn("labels", original_sense)

    def test_without_adapter_material_boundary_would_be_lost(self):
        # Documents the discovered gap: build_partitions() alone (no adapter) reads "labels",
        # so real evidence using "tags" collapses all senses into a single material partition.
        from vocab_consolidation import build_partitions

        partitions = build_partitions(synthesis_style_evidence())
        self.assertEqual(len(partitions), 1)
        self.assertEqual(partitions[0].material_partition, ())
        self.assertEqual(len(partitions[0].members), 3)


class LexicalDatasetIdentityTests(unittest.TestCase):
    def test_identity_uses_only_dataset_version_fields(self):
        evidence = synthesis_style_evidence()
        identity = lexical_dataset_identity_from_evidence(evidence)
        self.assertEqual(identity, {"wiktionary_versions": ["wiktionary-2024-01"], "wordnet_version": "wordnet-3.1"})

    def test_identity_is_deterministic(self):
        evidence = synthesis_style_evidence()
        self.assertEqual(
            lexical_dataset_identity_from_evidence(evidence),
            lexical_dataset_identity_from_evidence(evidence),
        )


if __name__ == "__main__":
    unittest.main()
