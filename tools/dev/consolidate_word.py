#!/usr/bin/env python3
"""Bounded developer entry point for word-level consolidation (M004.6.12).

Plans and, only if explicitly requested, executes `consolidate_word_evidence()` for one
word against the accepted lexical dataset and the durable consolidation persistence
boundary. This is a developer diagnostic tool only -- it is not a second UI, is not wired
into the Streamlit app or `LexicalWorkflow.search()`, and never loops over words or runs
unboundedly. Every live invocation requires an explicit `--max-total-pairs` budget.

Usage:
    # Report planned partitions/pair burden only -- makes zero Qwen calls, zero DB writes.
    python3 tools/dev/consolidate_word.py yak --plan-only

    # Execute against the durable consolidation persistence boundary, bounded to at most
    # 5 live Qwen calls total across all of the word's partitions.
    python3 tools/dev/consolidate_word.py yak --max-total-pairs 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_persistence():
    import psycopg
    from psycopg.rows import dict_row

    from vocab_consolidation_persistence import ConsolidationPersistence
    from vocab_migrations import apply_migrations

    db_password = os.environ["VOCAB_DB_PASSWORD"]
    connection = psycopg.connect(
        host=os.environ.get("VOCAB_DB_HOST", "vocab-db"),
        port=os.environ.get("VOCAB_DB_PORT", "5432"),
        dbname=os.environ.get("VOCAB_DB_NAME", "vocab"),
        user=os.environ.get("VOCAB_DB_USER", "vocab"),
        password=db_password,
        row_factory=dict_row,
    )
    apply_migrations(connection)
    return ConsolidationPersistence(connection), connection


def _load_evidence(word: str):
    from vocab_lexical_engine import lookup, resolve_active_database
    from vocab_synthesis import project_synthesis_evidence

    lexical_root = os.environ.get("VOCAB_LEXICAL_ROOT", str(Path.home() / ".local" / "share" / "vocab-lexical"))
    database_path = resolve_active_database(lexical_root)
    result = lookup(database_path, word)
    return project_synthesis_evidence(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("word", help="Word to consolidate (looked up via the accepted canonical lexical lookup).")
    parser.add_argument("--plan-only", action="store_true", help="Only report planned partitions/pair burden; make zero Qwen calls and zero persistence writes.")
    parser.add_argument("--max-total-pairs", type=int, default=None, help="Bound the number of live Qwen calls made across all partitions in this invocation.")
    args = parser.parse_args()

    if not args.plan_only and args.max_total_pairs is None:
        parser.error("--max-total-pairs is required unless --plan-only is set (never invoke unbounded live work).")

    from vocab_consolidation_workflow import plan_word_consolidation, total_expected_pair_count

    evidence = _load_evidence(args.word)
    partitions = plan_word_consolidation(evidence)
    plan_report = {
        "normalized_lemma": evidence.get("normalized_lemma"),
        "partition_count": len(partitions),
        "partitions": [
            {"partition_id": p.partition_id, "pos": p.pos, "material_partition": list(p.material_partition),
             "sense_count": len(p.members), "expected_pair_count": p.expected_pair_count}
            for p in partitions
        ],
        "total_expected_pair_count": total_expected_pair_count(partitions),
    }
    print(json.dumps(plan_report, indent=2))

    if args.plan_only:
        return 0

    from vocab_consolidation_provider import QWEN_EXPECTED_DIGEST, QWEN_MODEL, QWEN_SEMANTIC_OPTIONS, QwenPairProvider, confirm_installed_model_identity
    from vocab_consolidation_workflow import consolidate_word_evidence

    provider = QwenPairProvider()
    confirm_installed_model_identity(provider.endpoint, QWEN_MODEL, QWEN_EXPECTED_DIGEST)
    persistence, connection = _build_persistence()
    try:
        result = consolidate_word_evidence(
            persistence, evidence, provider,
            model_identity={"name": QWEN_MODEL, "digest": QWEN_EXPECTED_DIGEST}, semantic_options=QWEN_SEMANTIC_OPTIONS,
            max_total_pairs=args.max_total_pairs,
        )
        connection.commit()
    finally:
        connection.close()

    print(json.dumps({
        "word_status": result.word_status,
        "total_provider_calls_made": result.total_provider_calls_made,
        "total_reused_pair_count": result.total_reused_pair_count,
        "total_expected_pair_count": result.total_expected_pair_count,
        "partitions": [
            {"partition_id": p.partition_id, "pos": p.pos, "status": p.status,
             "provider_calls_made": p.provider_calls_made, "topology_identity": p.topology_identity,
             "container_count": len(p.containers)}
            for p in result.partitions
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
