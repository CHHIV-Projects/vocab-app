# M004.3 Real-Source Fixtures

These JSONL files are bounded raw Wiktextract records downloaded from Kaikki's
per-entry English JSONL endpoints on 2026-09-07. The pages identify the source
as an English Wiktionary extraction based on the 2026-09-02 enwiktionary dump,
using Wiktextract commit `ccec6f1` and Wikitextprocessor commit `4deed51`.

- `archipelago.jsonl`: https://kaikki.org/dictionary/English/meaning/a/ar/archipelago.jsonl
- `run.jsonl`: https://kaikki.org/dictionary/English/meaning/r/ru/run.jsonl
- `running.jsonl`: https://kaikki.org/dictionary/English/meaning/r/ru/running.jsonl

The importer records source path/line locators and SHA-256 hashes for each
source record. These fixtures are test evidence only; they are not production
lexical data and are not copied into the application image.