# Verification — 9 October 2026

The user authorized setup and verification after the earlier manual-only request.

- All dependencies and the small English spaCy model installed.
- `LUMI_REAL_MODELS=1 LUMI_PERFORMANCE=1 backend/.venv/bin/python -m pytest -q`: **44 passed**, including the real local Qwen cited-answer workflow, latency/memory tests, fallback extraction, and document-scoped graphs.
- Final production build: passed. Three.js is lazy loaded; its bundle still triggers Vite's size advisory.
- Live browser: checked upload dialog, document library, source-specific Open graph navigation, processing feedback and graph overview. Screenshot: [graph interface](benchmarks/screenshots/graph.jpg).
- The existing uploaded PDF (64 readable pages, 88 passages) completed with the new pipeline in **9.04 seconds**, publishing the initial graph in **1.17 seconds**, during concurrent checks. Recorded job: [existing-document.json](benchmarks/existing-document.json).
- Old Neo4j and embedding processes stopped; the generation-only local server, backend and frontend are running.

## Isolated generated document measurements

These runs included allocation tracking and overlapped other verification work. Each document used a disposable SQLite database and isolated worker. They are measurements of synthetic fixtures, not a promise for arbitrary documents.

| Fixture | Cold processing | Initial graph | Worker peak RSS |
| --- | --- | --- | --- |
| small.txt | 3.72 s | 3.71 s | 142 MB |
| small.docx | 2.25 s | 2.24 s | 165 MB |
| small.pdf | 4.09 s | 4.08 s | 130 MB |
| medium.txt | 6.82 s | 5.30 s | 135 MB |
| medium.docx | 3.96 s | 3.00 s | 165 MB |
| medium.pdf | 3.46 s | 2.29 s | 165 MB |

The small/medium synthetic entity gold set scored 1.0 precision and recall. This is a small sanity check, not real-document accuracy certification. Raw measurements: [after.json](benchmarks/after.json).

The old baseline contains an incomplete job at 1,472.18 seconds with 23 of 32 selected passages mapped. The new pipeline maps every readable passage. We do not report an exact speedup because the old run was incomplete and coverage differs.

## Chat submission and cleanup

Enter and the send arrow were verified in the live browser: the composer clears immediately and the sent question appears above it with a processing indicator. Failed sends retain a retry action. Shared submission handling prevents concurrent duplicate sends and respects IME composition. Unused website import code, Neo4j compatibility code, their obsolete tests/dependencies, and the old inference-cache ORM definition were removed. Existing documents and database contents were preserved.

## Citation numbering regression

The generation prompt now requests exact source markers such as `[S3]`; the server resolves those IDs to retrieved evidence and assigns display numbers itself. Older original-passage numeric markers are normalized as well. Ten regression cases cover reordered, repeated, missing and invalid markers; unknown sources remain rejected. The previously failing chain-of-thought question returned HTTP 200 with a citation to page 29 of the uploaded prompt-engineering PDF. All 44 tests passed, including the real local model and performance checks.
