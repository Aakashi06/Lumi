"""Opt-in performance budgets; run manually with LUMI_PERFORMANCE=1."""

import asyncio
import json
import os
import resource
import sys
import time
from uuid import uuid4

import pymupdf
import pytest
from sqlalchemy import select

from lumi.db import Chunk, EntitySpan, Job, Session, Source
from lumi.local_extraction import extract, normalize
from lumi.pipeline import Pipeline
from lumi.telemetry import Timings


class NoInference:
    async def generate(self, *args, **kwargs):
        raise AssertionError("Upload invoked an LLM")

    async def embed(self, *args, **kwargs):
        raise AssertionError("Upload invoked an embedding model")


def test_entities_and_relationships_have_literal_evidence():
    text = "SQLite uses Python. NetworkX requires Python. Retrieval uses embeddings."
    result = extract(text, Timings())
    expected = {"sqlite", "python", "networkx", "retrieval", "embeddings"}
    predicted = {hit["key"] for hit in result["hits"]}
    assert len(predicted & expected) / len(expected) >= 0.8
    assert len(predicted & expected) / max(len(predicted), 1) >= 0.8
    for hit in result["hits"]:
        assert text[hit["start"] : hit["end"]] == hit["name"]
    verified = [edge for edge in result["edges"] if edge["verified"]]
    assert any(edge["relation"] == "USES" for edge in verified)
    assert all(edge["quote"] in text and edge["kind"] == "semantic" for edge in verified)
    assert all(not edge["verified"] for edge in result["edges"] if edge["kind"] == "cooccurrence")
    assert normalize(" SQLite ") == normalize("SQLITE")


@pytest.mark.parametrize(
    "sentence",
    [
        "SQLite does not use Python.",
        "SQLite may use Python.",
        "If SQLite uses Python, NetworkX requires Python.",
        "Does SQLite use Python?",
        "SQLite and Python appear here.",
    ],
)
def test_cooccurrence_never_proves_a_semantic_relationship(sentence):
    result = extract(sentence, Timings())
    assert not any(edge["verified"] for edge in result["edges"])


@pytest.mark.skipif(os.getenv("LUMI_PERFORMANCE") != "1", reason="Manual performance run only")
@pytest.mark.parametrize("pages,budget", [(3, 15), (30, 30)])
def test_document_latency_memory_cache_and_provenance(tmp_path, pages, budget, record_property):
    path = tmp_path / "fixture.pdf"
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page().insert_textbox(
                pymupdf.Rect(40, 40, 550, 800),
                "SQLite uses Python. NetworkX requires Python. Retrieval uses embeddings. " * 20,
            )
        document.save(path)
    with Session.begin() as session:
        source = Source(id=str(uuid4()), kind="pdf", title=path.name, file_path=str(path))
        session.add(source)
        session.flush()
        job = Job(id=str(uuid4()), source_id=source.id)
        session.add(job)
        job_id, source_id = job.id, source.id
    start = time.perf_counter()
    asyncio.run(Pipeline(NoInference()).run(job_id))
    duration = time.perf_counter() - start
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024**2 if sys.platform == "darwin" else 1024
    )
    record_property("duration_seconds", duration)
    record_property("peak_rss_mb", rss)
    assert duration < float(os.getenv("LUMI_MAX_PROCESS_SECONDS", str(budget)))
    assert rss < float(os.getenv("LUMI_MAX_RSS_MB", "600"))
    with Session() as session:
        job = session.get(Job, job_id)
        assert job.stage == "completed", job.error
        summary = json.loads(job.summary)
        assert summary["initial_graph_ms"] < duration * 1000 + 1
        assert summary["graph_chunks"] == summary["chunks"]
        assert set(summary["timings_ms"]) >= {
            "document_parsing",
            "chunking",
            "entity_extraction",
            "relationship_extraction",
            "embedding_generation",
            "graph_construction",
            "serialization",
        }
        for span, chunk in session.execute(select(EntitySpan, Chunk).join(Chunk)):
            assert chunk.text[span.start : span.end] == span.text
    with Session.begin() as session:
        retry = Job(id=str(uuid4()), source_id=source_id)
        session.add(retry)
        retry_id = retry.id
    asyncio.run(Pipeline(NoInference()).run(retry_id))
    with Session() as session:
        summary = json.loads(session.get(Job, retry_id).summary)
        assert summary["unchanged"] and summary["cache_misses"] == 0


def test_rules_only_fallback_does_not_require_a_tagger(monkeypatch):
    from lumi import local_extraction

    monkeypatch.setattr(local_extraction.settings, "spacy_model", "missing-model-for-test")
    local_extraction.engine.cache_clear()
    try:
        result = local_extraction.extract("SQLite uses Python.", Timings())
        assert {hit["key"] for hit in result["hits"]} == {"sqlite", "python"}
        assert "rules-only" in result["engine"]
    finally:
        local_extraction.engine.cache_clear()


def test_repeated_pdf_navigation_is_not_a_concept():
    result = extract(
        "Section 1 Section 3 Section 2: How agents work. SQLite uses Python.", Timings()
    )
    assert not any("section 1 section 3" in hit["key"] for hit in result["hits"])
    assert any(hit["key"] == "sqlite" for hit in result["hits"])
