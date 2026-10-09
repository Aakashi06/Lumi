# Lumi

Local document knowledge graphs from PDF, Word `.docx`, and UTF-8 `.txt` / `.md`. Explore concepts in 3D and ask local Qwen questions with document citations.

## Run

Requires Python 3.13 and Node.js. llama.cpp and the existing generation GGUF are needed only for Ask Lumi. There are no hosted API calls or API keys.

```sh
make setup
make backend
make frontend
# In another terminal, only when using Ask Lumi:
make models
```

Open [Lumi](http://127.0.0.1:5173/). SQLite is embedded; Neo4j and Java are no longer required. Existing SQLite documents and conversations are preserved by an additive migration. Completed documents are not automatically reprocessed: choose Retry in the library to remap an older document with the new extractor.

For an existing installation, install the added dependencies and English model before restarting the backend:

```sh
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m spacy download en_core_web_sm
```

## Pipeline

1. Hash file contents; skip unchanged documents with the same extraction version.
2. Reuse parsed-document caches, or parse with PyMuPDF / python-docx / UTF-8 text.
3. Chunk with page and character references. Publish all readable text into SQLite FTS5.
4. Extract entities with the small English spaCy model, technical phrases, and bounded noun phrases. No generative inference or embeddings are required for uploads.
5. Build and persist a NetworkX batch for four representative passages; enrich remaining passages in background batches of eight. One NLP worker and CPU pools capped at two threads bound resource use.
6. Deduplicate normalized entity keys, retain every accepted occurrence with chunk-local offsets and source provenance, and cache extraction by text hash plus pipeline/model version.
7. Fetch 75 ranked concepts initially. Select a concept and choose **Show connections in graph** to expand to at most 200 concepts. Source markers are bounded separately to 20. React/Three.js retain the existing design, zoom and orbit controls.
8. Answer questions from full-document FTS5 passages, even before graph enrichment finishes. The existing local generation model is used only for answers, with validated citation IDs and PDF page links.

**Relationship meanings:** dashed co-occurrence links mean two entities appear in the same sentence; they do not prove a semantic relationship. Solid links marked “stated in source” require a conservative literal statement rule. This verifies the statement's presence, not its truth in the world. Legacy model relationships remain explicitly unverified. Rules deliberately omit ambiguous, negated, conditional and question statements.

`LUMI_ENABLE_EMBEDDINGS=false` is the default for an 8GB Mac. Optional embedding generation runs sequentially after graph completion and has a 15-second request timeout. Turning it on requires a separately started local embedding server; `make models` starts only generation. Q&A retains lexical retrieval without embeddings. The existing 4B generation weights are unchanged; close other memory-heavy applications when asking questions.

## Timings and manual verification

Setup and verification are complete: **44 tests passed**, including the local Q&A and performance checks, and the production build passed. See [verification results](VERIFICATION.md) and [benchmark details](benchmarks/README.md). Job summaries expose per-stage timings, initial graph time and cache counts. `/api/performance` exposes recent JSON serialization metrics; the browser console's `window.lumiPerformance()` exposes React render and graph layout timings.

## Limits

12 MB uploads, 300 PDF pages, 1,200 chunks, and 50 MB uncompressed DOCX archives. Scanned PDFs need OCR first. Legacy `.doc` needs conversion to `.docx`. YouTube, web and repository imports remain disabled; legacy source data remains stored but outside the active workspace. Entity extraction currently targets English; rule-only fallback is disclosed in job summaries when the spaCy model is missing.
# Lumi
