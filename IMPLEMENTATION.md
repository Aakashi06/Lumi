# Document graph implementation

The current pipeline uses PyMuPDF, python-docx, spaCy's small English NER model, technical phrase matching, conservative statement rules, NetworkX batch construction, SQLite storage and FTS5 retrieval. See [README](README.md) for the data flow, limits and relationship semantics.

The pipeline does not call an LLM during ingestion. Four representative chunks publish an initial graph, followed by all remaining chunks in batches of eight. Hash/version caches reuse parsing and extraction; unchanged document retries skip processing. Changed documents update only their own chunks, mentions, spans and edges. Source deletion reranks affected concepts rather than rebuilding the graph.

Entity spans use Unicode character offsets within parsed text. PDF offsets are relative to their page; DOCX/text offsets refer to the parser's document text. Chunks retain their starting offsets; concept evidence exposes absolute spans in that scope. Shared concepts keep independent document mentions and occurrence spans.

Graph responses start with 75 important concepts and are bounded to 200 when expanded. Importance counts document-chunk mentions and source-stated relationships. Co-occurrence is labeled and dashed; it does not contribute semantic relationship weight. Legacy LLM relationships remain unverified.

Question answering still uses the configured loopback generation server and validated document-grounded citations. Embeddings are optional and disabled by default. The model launcher starts generation only, removing the second model's default memory cost.

Timings and manual benchmark instructions are in [benchmarks/README.md](benchmarks/README.md). After the user authorized full setup and verification, 44 tests and the production build passed. Measured results are in [VERIFICATION.md](VERIFICATION.md).
