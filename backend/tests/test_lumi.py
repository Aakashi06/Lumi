import asyncio
import json
import time
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from lumi import main, parsing, pipeline
from lumi.chunking import chunk_passages
from lumi.config import Settings
from lumi.contracts import Extraction
from lumi.db import Chunk, Concept, Edge, Job, Session, Source
from lumi.graph import normalize, position
from lumi.parsing import Passage
from lumi.pipeline import Pipeline
from lumi.retrieval import answer, search
from pydantic import ValidationError
from sqlalchemy import func, select

TEST_FILES = tempfile.TemporaryDirectory(prefix="lumi-test-files-")

TEXT = "Retrieval uses embeddings to find relevant documents. Embeddings represent text as numeric vectors."


def extraction():
    return {
        "concepts": [
            {
                "name": "Retrieval",
                "description": "Finding relevant documents.",
                "domain": "AI",
                "quote": "Retrieval uses embeddings",
            },
            {
                "name": "Embeddings",
                "description": "Numeric text representations.",
                "domain": "AI",
                "quote": "Embeddings represent text as numeric vectors.",
            },
        ],
        "relationships": [
            {
                "source": "Retrieval",
                "target": "Embeddings",
                "relation": "USES",
                "quote": "Retrieval uses embeddings to find relevant documents.",
                "confidence": 0.95,
            }
        ],
    }


class FakeModels:
    def __init__(self):
        self.calls = 0

    async def embed(self, texts):
        return [[1.0, 0.5, 0.2] for _ in texts]

    async def generate(self, system, prompt, schema=None, max_tokens=None):
        self.calls += 1
        if "citation_ids" in system:
            evidence = json.loads(prompt)["evidence"]
            return {
                "answer": "Retrieval uses embeddings to find documents [1].",
                "citation_ids": [evidence[0]["id"]],
            }
        return extraction()


async def fake_reader(*args):
    return "Test knowledge", [Passage(TEXT, {"page": 2})]


def seed_job(source_id=None):
    path = Path(TEST_FILES.name) / f"{uuid4()}.pdf"
    path.write_text(TEXT)
    with Session.begin() as session:
        source = Source(
            id=source_id or str(uuid4()),
            kind="pdf",
            title="Test source",
            file_path=str(path),
        )
        session.add(source)
        session.flush()
        job = Job(id=str(uuid4()), source_id=source.id)
        session.add(job)
        return source.id, job.id


def run_ingestion(monkeypatch, models=None):
    monkeypatch.setattr(pipeline, "read_source", fake_reader)
    source_id, job_id = seed_job()
    asyncio.run(Pipeline(models or FakeModels()).run(job_id))
    return source_id, job_id


def test_chunking_preserves_page_and_lines():
    chunks = chunk_passages(
        [
            Passage("line one\nline two\n" * 400, {"path": "src/main.py", "line_start": 10}),
            Passage(TEXT, {"page": 3}),
        ],
        size=100,
    )
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[1].reference["line_start"] > 10
    assert chunks[-1].reference["page"] == 3
    assert chunks[-1].reference["char_end"] == len(TEXT)
    assert all(c.reference["line_end"] >= c.reference["line_start"] for c in chunks[:-1])


def test_pdf_reader_and_scan_failure(tmp_path):
    path = tmp_path / "reading.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((50, 50), TEXT)
    document.save(path)
    title, passages = parsing.pdf(str(path))
    assert title == "reading" and "Retrieval" in passages[0].text
    assert passages[0].reference["page"] == 1
    blank = tmp_path / "blank.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(blank)
    with pytest.raises(ValueError, match="OCR"):
        parsing.pdf(str(blank))


def test_structured_extraction_validation():
    bad = extraction()
    bad["relationships"][0]["relation"] = "INVENTED"
    with pytest.raises(ValidationError):
        Extraction.model_validate(bad)
    assert normalize("  EMBEDDINGS  ") == "embeddings"
    assert position("retrieval", "AI") == position("retrieval", "AI")


def test_full_workflow_incremental_delete_and_citations(monkeypatch):
    models = FakeModels()
    first, first_job = run_ingestion(monkeypatch, models)
    second, _ = run_ingestion(monkeypatch, models)
    with Session() as session:
        assert session.get(Job, first_job).stage == "completed"
        assert {c.name.casefold() for c in session.scalars(select(Concept))} >= {
            "retrieval",
            "embeddings",
        }
    assert models.calls == 0
    result = asyncio.run(answer("How are retrieval and embeddings connected?", models))
    assert result["citations"][0]["reference"]["page"] == 2
    with TestClient(main.app) as client:
        graph = client.get("/api/graph").json()
        node = next(n for n in graph["nodes"] if n["name"].casefold() == "retrieval")
        assert len(client.get(f"/api/graph/concepts/{node['id']}").json()["evidence"]) == 2
        assert client.get(f"/api/graph/concepts/{node['id']}/neighbors").json()
        assert client.delete(f"/api/sources/{first}").status_code == 204
        remaining = client.get("/api/graph").json()
        assert len(remaining["nodes"]) == len(graph["nodes"])
        assert all(node["source_ids"] == [second] for node in remaining["nodes"])
        assert client.delete(f"/api/sources/{second}").status_code == 204
        empty = client.get("/api/graph").json()
        assert not empty["nodes"] and not empty["edges"]


def test_unchanged_resource_skips_models(monkeypatch):
    models = FakeModels()
    source_id, _ = run_ingestion(monkeypatch, models)
    calls = models.calls
    with Session.begin() as session:
        job = Job(id=str(uuid4()), source_id=source_id)
        session.add(job)
        job_id = job.id
    asyncio.run(Pipeline(models).run(job_id))
    assert models.calls == calls
    with Session() as session:
        assert session.get(Job, job_id).stage == "completed"
        assert session.scalar(select(func.count()).select_from(Chunk)) == 1


def test_parse_failure_preserves_previous_document(monkeypatch):
    source_id, _ = run_ingestion(monkeypatch)

    async def unreadable(*args):
        raise ValueError("Document is unreadable")

    monkeypatch.setattr(pipeline, "read_source", unreadable)
    with Session.begin() as session:
        source = session.get(Source, source_id)
        Path(source.file_path).write_text("Changed bytes")
        job = Job(id=str(uuid4()), source_id=source_id)
        session.add(job)
        job_id = job.id
    asyncio.run(Pipeline(FakeModels()).run(job_id))
    with Session() as session:
        assert session.get(Job, job_id).stage == "failed"
        assert session.scalar(select(Chunk.text)) == TEXT
        assert session.scalar(select(func.count()).select_from(Edge)) >= 1


def test_ingestion_does_not_require_model_servers(monkeypatch):
    class OfflineModels(FakeModels):
        async def embed(self, *args):
            raise AssertionError("Embedding server must not be called")

        async def generate(self, *args, **kwargs):
            raise AssertionError("LLM must not be called")

    _, job_id = run_ingestion(monkeypatch, OfflineModels())
    with Session() as session:
        assert session.get(Job, job_id).stage == "completed"
        assert json.loads(session.get(Job, job_id).summary)["embedding_status"] == "disabled"
        assert session.scalar(select(func.count()).select_from(Concept)) >= 2


def test_retrieval_keyword_fallback_and_empty_answer(monkeypatch):
    class OfflineModels(FakeModels):
        async def embed(self, *args):
            raise httpx.ConnectError("offline")

    run_ingestion(monkeypatch)
    results, mode = asyncio.run(search("embeddings", 6, OfflineModels()))
    assert results and "keyword" in mode
    results, _ = asyncio.run(search("bananas", 6, OfflineModels()))
    assert not results
    assert not asyncio.run(answer("bananas", OfflineModels()))["citations"]


def test_fake_citation_rejected(monkeypatch):
    class BadCitations(FakeModels):
        async def generate(self, *args, **kwargs):
            return {"answer": "Made up [1].", "citation_ids": ["not-a-real-chunk"]}

    run_ingestion(monkeypatch)
    with pytest.raises(ValueError, match="not present"):
        asyncio.run(answer("embeddings", BadCitations()))


def test_api_upload_chat_validation_and_retry(monkeypatch):
    fake = FakeModels()
    monkeypatch.setattr(main, "models", fake)
    monkeypatch.setattr(main, "pipeline", Pipeline(fake))
    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200
        assert (
            client.post("/api/sources/url", json={"kind": "blog", "url": "bad"}).status_code == 405
        )
        assert client.post("/api/search", json={"query": "", "limit": 50}).status_code == 422
        assert (
            client.post("/api/sources/pdf", files={"file": ("bad.pdf", b"not pdf")}).status_code
            == 422
        )
        doc = pymupdf.open()
        doc.new_page().insert_text((50, 50), TEXT)
        uploaded = client.post(
            "/api/sources/pdf",
            files={"file": ("reading.pdf", doc.tobytes(), "application/pdf")},
        )
        assert uploaded.status_code == 202
        job_id = uploaded.json()["job_id"]
        source_id = uploaded.json()["source"]["id"]
        for _ in range(500):
            status = client.get(f"/api/jobs/{job_id}").json()["stage"]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert status == "completed"
        assert (
            client.get(f"/api/sources/{source_id}/file").headers["content-type"]
            == "application/pdf"
        )
        graph = client.get("/api/graph").json()
        assert len(graph["nodes"]) >= 2 and graph["nodes"][0]["source_ids"] == [source_id]
        response = client.post("/api/chat", json={"query": "How does retrieval use embeddings?"})
        assert response.status_code == 200 and response.json()["citations"]
        assert len(client.get("/api/chat").json()) == 1
        assert client.get("/api/graph/concepts/missing").status_code == 404
        assert client.post(f"/api/sources/{source_id}/retry").status_code == 202
        for _ in range(500):
            if client.get(f"/api/sources/{source_id}").json()["status"] in {
                "completed",
                "failed",
            }:
                break
            time.sleep(0.02)
        assert client.delete(f"/api/sources/{source_id}").status_code == 204


def test_local_only_model_configuration():
    with pytest.raises(ValidationError):
        Settings(model_url="https://openrouter.ai/api/v1")


def test_parser_whitespace_is_tolerated_but_joined_quotes_are_not():
    from lumi.graph import verify_extraction

    original = extraction()
    wrapped = TEXT.replace("numeric vectors", "numeric\nvectors")
    verified = verify_extraction(wrapped, Extraction.model_validate(original))
    assert "numeric\nvectors" in verified.concepts[1].quote
    original["concepts"][0]["quote"] = "Retrieval uses embeddings. Embeddings represent text"
    with pytest.raises(ValueError, match="contiguous"):
        verify_extraction(TEXT, Extraction.model_validate(original))


def test_valid_citation_ids_receive_deterministic_markers(monkeypatch):
    class MissingMarkers(FakeModels):
        async def generate(self, system, prompt, schema=None, max_tokens=None):
            evidence = json.loads(prompt)["evidence"]
            return {"answer": "Retrieval uses embeddings.", "citation_ids": [evidence[0]["id"]]}

    run_ingestion(monkeypatch)
    result = asyncio.run(answer("embeddings", MissingMarkers()))
    assert result["answer"].endswith("[1]") and result["citations"][0]["id"]


def test_passages_are_searchable_before_graph_finishes(monkeypatch):
    import threading

    monkeypatch.setattr(pipeline, "read_source", fake_reader)
    source_id, job_id = seed_job()
    entered, gate = threading.Event(), threading.Event()
    runner = Pipeline(FakeModels())
    original = runner.batch

    def waiting_batch(*args):
        entered.set()
        if not gate.wait(10):
            raise TimeoutError("Test did not release extraction")
        return original(*args)

    monkeypatch.setattr(runner, "batch", waiting_batch)

    async def scenario():
        task = asyncio.create_task(runner.run(job_id))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            results, mode = await search("embeddings", 5, FakeModels())
            assert results and results[0]["source_id"] == source_id
            assert mode == "keyword"
        finally:
            gate.set()
            await task

    asyncio.run(scenario())


def test_duplicate_upload_reuses_document_and_extraction_cache(monkeypatch):
    run_ingestion(monkeypatch)
    _, job_id = run_ingestion(monkeypatch)
    with Session() as session:
        summary = json.loads(session.get(Job, job_id).summary)
        assert summary["document_cache_hit"]
        assert summary["cache_hits"] == summary["chunks"]
        assert summary["cache_misses"] == 0
        assert session.scalar(select(func.count()).select_from(Chunk)) == 2


def test_repeated_question_does_not_reembed_documents(monkeypatch):
    class EmbeddingCounter(FakeModels):
        def __init__(self):
            super().__init__()
            self.embedding_calls = 0

        async def embed(self, texts):
            self.embedding_calls += 1
            return await super().embed(texts)

    models = EmbeddingCounter()
    run_ingestion(monkeypatch, models)
    calls = models.embedding_calls
    asyncio.run(answer("What are embeddings?", models))
    asyncio.run(answer("What are embeddings?", models))
    assert models.embedding_calls == calls


def test_document_title_outweighs_a_page_of_related_links(monkeypatch):
    source_id, _ = seed_job()
    with Session.begin() as session:
        for identifier, text, heading, title, url in [
            (
                "answer",
                "A giant instruction file buries the important rules in noise and consumes context. Split instructions into focused files.",
                "Why one giant instruction file fails",
                "Why one giant instruction file fails",
                "https://docs.example/lecture-04/#why-one-giant-instruction-file-fails",
            ),
            (
                "links",
                "Why one giant instruction file fails. Giant instruction file links and references. One giant instruction file.",
                "References (Original sources)",
                "Other tool design",
                "https://docs.example/other/#references",
            ),
        ]:
            session.add(
                Chunk(
                    id=identifier,
                    source_id=source_id,
                    text=text,
                    reference=json.dumps({"heading": heading, "title": title, "url": url}),
                    embedding="[]",
                    embedding_model="none",
                )
            )
    results, _ = asyncio.run(search("Why does one giant instruction file fail?", 2, FakeModels()))
    assert results[0]["id"] == "answer"
    assert results[0]["reference"]["url"].endswith("#why-one-giant-instruction-file-fails")


def test_refresh_reports_the_new_index_size(monkeypatch):
    source_id, _ = run_ingestion(monkeypatch)

    async def changed(*args):
        return "Expanded", [
            Passage(TEXT, {"page": 1}),
            Passage(TEXT + " Added explanation.", {"page": 2}),
        ]

    monkeypatch.setattr(pipeline, "read_source", changed)
    with Session.begin() as session:
        Path(session.get(Source, source_id).file_path).write_text(TEXT + " Changed bytes")
        job = Job(id=str(uuid4()), source_id=source_id)
        session.add(job)
        job_id = job.id
    asyncio.run(Pipeline(FakeModels()).run(job_id))
    with Session() as session:
        result = session.get(Job, job_id)
        assert result.stage == "completed"
        assert json.loads(result.summary)["indexed_chunks"] == 2
        assert session.scalar(select(func.count()).select_from(Chunk)) == 2


def test_comparison_without_explicit_evidence_is_flagged_for_review():
    from lumi.graph import verify_extraction

    result = extraction()
    result["relationships"][0]["relation"] = "COMPARES_WITH"
    verified = verify_extraction(TEXT, Extraction.model_validate(result))
    assert verified.relationships[0].confidence < 0.75


def test_unproven_relationship_keeps_source_entities():
    from lumi.local_extraction import extract
    from lumi.telemetry import Timings

    result = extract("Retrieval and embeddings appear in this example.", Timings())
    assert {h["key"] for h in result["hits"]} >= {"retrieval", "embeddings"}
    assert not any(e["verified"] for e in result["edges"])
    assert any(e["kind"] == "cooccurrence" for e in result["edges"])


@pytest.mark.parametrize("extension", ["txt", "docx"])
def test_document_upload_to_sqlite(monkeypatch, extension):
    from io import BytesIO

    from docx import Document
    from lumi.graph_store import read_graph

    fake = FakeModels()
    monkeypatch.setattr(main, "models", fake)
    monkeypatch.setattr(main, "pipeline", Pipeline(fake))
    data = TEXT.encode()
    if extension == "docx":
        document = Document()
        document.add_paragraph(TEXT)
        output = BytesIO()
        document.save(output)
        data = output.getvalue()
    with TestClient(main.app) as client:
        result = client.post("/api/sources/upload", files={"file": (f"notes.{extension}", data)})
        assert result.status_code == 202
        for _ in range(500):
            job = client.get("/api/jobs/" + result.json()["job_id"]).json()
            if job["stage"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert job["stage"] == "completed", job
        graph = read_graph()
        assert len(graph["nodes"]) >= 2 and graph["edges"]
        assert client.get("/api/graph/concepts/" + graph["nodes"][0]["id"]).json()["evidence"]
        assert (
            client.post(
                "/api/sources/upload", files={"file": ("bad.doc", b"unsupported")}
            ).status_code
            == 422
        )


def test_graph_source_scope_excludes_other_documents_and_expanded_nodes(monkeypatch):
    from lumi.graph_store import read_graph

    first, _ = run_ingestion(monkeypatch)

    async def other_reader(*args):
        return "Other", [Passage("SQLite uses Python. NetworkX requires Python.", {"page": 1})]

    monkeypatch.setattr(pipeline, "read_source", other_reader)
    second, job_id = seed_job()
    with Session() as session:
        Path(session.get(Source, second).file_path).write_text("Different source bytes")
    asyncio.run(Pipeline(FakeModels()).run(job_id))
    graph = read_graph(source_id=first)
    other = read_graph(source_id=second)
    assert graph["nodes"] and other["nodes"]
    assert all(first in node["source_ids"] for node in graph["nodes"])
    assert all(second in node["source_ids"] for node in other["nodes"])
    foreign_ids = [node["id"] for node in other["nodes"] if first not in node["source_ids"]]
    expanded = read_graph(source_id=first, expand=foreign_ids)
    assert all(first in node["source_ids"] for node in expanded["nodes"])


@pytest.mark.parametrize(
    "text,ids,expected,order",
    [
        ("Supported [S3] and [S1].", ["S3", "S1"], "Supported [1] and [2].", ["S3", "S1"]),
        ("Supported [3] and [1].", ["S3", "S1"], "Supported [1] and [2].", ["S3", "S1"]),
        ("Supported [1] and [2].", ["S3", "S1"], "Supported [1] and [2].", ["S3", "S1"]),
        ("Supported [S3] again [S3].", ["S3", "S3"], "Supported [1] again [1].", ["S3"]),
        ("Supported [S2].", ["S1"], "Supported [1].", ["S2", "S1"]),
        ("Supported.", ["S3"], "Supported. [1]", ["S3"]),
    ],
)
def test_source_ids_are_converted_to_display_numbers(text, ids, expected, order):
    from lumi.contracts import Answer
    from lumi.retrieval import format_citations

    evidence = {f"S{i}": {"id": f"S{i}"} for i in range(1, 4)}
    answer_text, citations = format_citations(Answer(answer=text, citation_ids=ids), evidence)
    assert answer_text == expected
    assert [item["id"] for item in citations] == order


@pytest.mark.parametrize(
    "text,ids",
    [
        ("Invented [S99].", ["S1"]),
        ("Invented [99].", ["S1"]),
        ("Invented [0].", ["S1"]),
        ("Invented [S1].", ["S99"]),
    ],
)
def test_citation_formatting_never_accepts_unknown_sources(text, ids):
    from lumi.contracts import Answer
    from lumi.retrieval import format_citations

    with pytest.raises(ValueError, match="not present"):
        format_citations(Answer(answer=text, citation_ids=ids), {"S1": {"id": "real"}})
