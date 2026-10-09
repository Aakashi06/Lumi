# Manual performance verification

The user subsequently authorized setup and verification: 44 tests and the production build passed. Measurements are saved in `after.json`; the existing uploaded PDF job is saved in `existing-document.json`. See [verification results](../VERIFICATION.md). `baseline.json` captures previously recorded jobs from the old pipeline. The PDF observation is **1,472.18 seconds with 23 of 32 selected passages mapped**; it is incomplete, so it cannot establish a completed-document speedup. Old memory and stage timings were not recorded.

## Manual workflow

1. Install the dependencies and `en_core_web_sm` using the commands in the root README; restart the backend. Start `make models` for Q&A only. The frontend dev server can use the existing project without a production build.
2. Upload a 3-page and a 20–30-page PDF, then DOCX and text documents. Observe the first concepts before the “enriching” stage completes. Check `/api/jobs` for `initial_graph_ms`, `timings_ms`, all-chunk coverage, and cache hits.
3. Select a concept, inspect source quotes, expand connections, zoom and orbit. Dashed lines mean same-sentence co-occurrence; “stated in source” links must have literal supporting text. Ask a question and open its source citation with the existing local generation server running.
4. Retry an unchanged completed document: its summary should report `unchanged=true` and zero extraction misses. Upload identical bytes again: the new source retains its own provenance while using document/extraction caches.
5. In the browser console run `window.lumiPerformance()` for bounded React CPU render and layout measurements. These are not GPU timings. JSON serialization measurements are available at `/api/performance` and in `Server-Timing` response headers.

## Optional measurement commands — run yourself

```sh
# Generates small and medium PDF, DOCX and text fixtures in temporary storage.
# Each file gets its own process and disposable SQLite database.
make benchmark

# Measure your real PDF without modifying the application database:
backend/.venv/bin/python scripts/benchmark.py \
  --document '/absolute/path/to/document.pdf' --output benchmarks/my-document.json

# Correctness checks; local model inference is mocked except the opt-in real-model test:
make test

# Opt-in small/medium latency and native-memory budgets:
LUMI_PERFORMANCE=1 backend/.venv/bin/python -m pytest backend/tests/test_performance.py -v
```

The JSON reports cold processing (including NLP loading), initial graph latency, cached upload, unchanged retry, stage durations, graph read/JSON serialization, native peak RSS, Python allocation peak, and a synthetic gold entity/relationship check. Python allocation tracking adds overhead; compare runs under the same conditions. Native RSS includes extension memory, while Python allocations alone do not. Frontend and the separate Qwen server are outside the worker's RSS; use macOS Activity Monitor to observe whole-system memory and swap.

A baseline matches only an identical file hash. The runner calculates a speedup only when both runs completed; otherwise it returns `null`. A before/after claim requires a genuine completed old run of the same file and workload. Old processing mapped only 32 passages; the new pipeline processes all readable passages, so coverage differs and should be reported alongside timing.

The 3-page/30-page tests have configurable 15/30-second duration and 600 MB process RSS budgets, not claimed measured outcomes. Configure `LUMI_MAX_PROCESS_SECONDS` / `LUMI_MAX_RSS_MB` for your machine. Synthetic precision/recall does not replace evaluation on your actual documents. No new large model or paid API is used.
