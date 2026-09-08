"""Bounded live M004.4 probe; this is not learner-facing application code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vocab_lexical_engine import resolve_active_database
from vocab_synthesis import OllamaProvider, SynthesisRuntime, synthesize_word


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("word")
    parser.add_argument("--lexical-root", default="/home/chuck/.local/share/vocab-lexical")
    parser.add_argument("--runtime-root", default="/home/chuck/.local/share/vocab-app/runtime")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--seed", type=int, default=424244)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--target-tokens", type=int, default=5000)
    args = parser.parse_args()
    provider = OllamaProvider(endpoint=args.endpoint)
    try:
        result = synthesize_word(resolve_active_database(Path(args.lexical_root)), args.word, provider, SynthesisRuntime(args.runtime_root), seed=args.seed, target_tokens=args.target_tokens, retry=args.retry)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": getattr(error, "code", "provider_failure"), "message": str(error), "details": getattr(error, "details", {})}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())