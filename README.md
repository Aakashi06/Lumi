 <div align="center">

# Lumi

### Your knowledge, connected.

**A local-first AI knowledge graph that transforms documents into connected concepts, interactive 3D visualizations, and source-grounded answers.**

`Knowledge Graphs` · `RAG` · `Local LLMs` · `NLP` · `Three.js`

</div>

![Lumi](https://github.com/user-attachments/assets/b9e5421b-5461-4caf-b310-5cc9aa2b4538)

## Overview

Lumi is a local-first document intelligence system that converts PDFs, Word documents, and text files into interactive knowledge graphs.

It combines NLP-based entity extraction, relationship mapping, and retrieval-augmented generation (RAG) to help users explore connected information and ask questions with document citations — entirely offline, without external APIs.

## Features

- **Knowledge Graph Generation** — Extracts entities and relationships from uploaded documents using spaCy and NetworkX.
- **Interactive 3D Visualization** — Explore connected concepts through a React and Three.js interface.
- **Local RAG** — Ask document-grounded questions using Qwen 4B, llama.cpp, and SQLite FTS5 retrieval.
- **Source Citations** — Trace answers to original document passages and PDF pages.
- **Optimized Processing** — Content hashing, extraction caching, and background graph enrichment for faster initial visualization.
- **Privacy-First** — Local processing, inference, and storage with no hosted API dependencies.

## Tech Stack

| Component | Technologies |
|---|---|
| Frontend | React, Three.js |
| Backend | Python 3.13 |
| NLP | spaCy |
| Knowledge Graph | NetworkX |
| LLM | Qwen 4B, llama.cpp |
| Retrieval | SQLite FTS5 |
| Database | SQLite |
| Document Processing | PyMuPDF, python-docx |

## Architecture

```text
             PDF / DOCX / TXT / MD
                      |
              Document Parsing
                      |
               Text Chunking
                      |
              Entity Extraction
                (spaCy + NLP)
                      |
            Relationship Mapping
                 (NetworkX)
                      |
              Knowledge Graph
                      |
            3D Graph Visualization

              User Question
                      |
            SQLite FTS5 Retrieval
                      |
              Retrieved Context
                      |
               Local Qwen 4B
                      |
          Answer + Source Citations
```

## Getting Started

**Requirements:** Python 3.13, Node.js, and Make.

```bash
git clone <repository-url>
cd Lumi

make setup
make backend
make frontend
```

Open `http://127.0.0.1:5173/`

For local AI-powered Q&A, start the model in another terminal:

```bash
make models
```

No API keys, Neo4j, or cloud services required.

## Performance & Evaluation

- **44 automated tests passed**, including Q&A and performance checks.
- Incremental graph construction with background enrichment.
- Cached document extraction to avoid redundant processing.
- CPU-constrained processing optimized for 8GB consumer hardware.
- Backend and frontend performance instrumentation.

See [Verification Results](VERIFICATION.md) and [Benchmarks](benchmarks/README.md).

