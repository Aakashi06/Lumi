"""Hash-cached, progressive document ingestion. No LLM on the upload path."""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, func, select

from .chunking import chunk_passages
from .config import settings
from .db import (
    Chunk,
    DocumentCache,
    Edge,
    EntitySpan,
    ExtractionCache,
    Job,
    Mention,
    Session,
    Source,
    now,
)
from .graph import prune_orphans
from .graph_store import persist, rerank
from .local_extraction import cache_key, extract, version
from .parsing import Passage, read_source
from .telemetry import Timings


def content_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class Pipeline:
    def __init__(self, models):
        self.models = models  # Used only for explicitly enabled optional embeddings.
        self.lock = asyncio.Lock()

    def stage(self, job_id, stage, error=None):
        with Session.begin() as session:
            job = session.get(Job, job_id)
            if job:
                source = session.get(Source, job.source_id)
                job.stage = source.status = stage
                job.error = source.error = error

    def progress(self, job_id, summary, started):
        with Session.begin() as session:
            job = session.get(Job, job_id)
            if job:
                job.summary = json.dumps(summary)
                job.elapsed_seconds = round(time.perf_counter() - started, 3)

    def batch(self, chunk_ids, timings):
        hits = misses = added = connections = 0
        with Session.begin() as session:
            for chunk_id in chunk_ids:
                chunk = session.get(Chunk, chunk_id)
                key = cache_key(chunk.text)
                cached = session.get(ExtractionCache, key)
                if cached:
                    result = json.loads(cached.result)
                    hits += 1
                else:
                    result = extract(chunk.text, timings)
                    with timings.measure("serialization"):
                        encoded = json.dumps(result)
                    session.add(ExtractionCache(id=key, result=encoded))
                    misses += 1
                with timings.measure("graph_construction"):
                    a, b = persist(session, chunk, result)
                    added += a
                    connections += b
        return hits, misses, added, connections

    async def run(self, job_id):
        started, timings = time.perf_counter(), Timings()
        summary = {
            "timings_ms": timings.values(),
            "embedding_status": "disabled",
            "graph_chunks": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "new_concepts": 0,
            "new_connections": 0,
        }
        try:
            with Session() as session:
                job = session.get(Job, job_id)
                if not job:
                    return
                source = session.get(Source, job.source_id)
                source_id, kind, path = (
                    source.id,
                    source.kind,
                    source.file_path,
                )
                previous_hash, previous_version = source.content_hash, source.pipeline_version
            self.stage(job_id, "extracting")
            digest = await asyncio.to_thread(content_hash, path)
            # Serialize NLP use and load one small model, never a model per document.
            async with self.lock:
                with timings.measure("nlp_model_load"):
                    pipeline_version = await asyncio.to_thread(version)
                if digest == previous_hash and pipeline_version == previous_version:
                    summary["unchanged"] = True
                    summary["timings_ms"] = timings.values()
                    self.stage(job_id, "completed")
                    self.progress(job_id, summary, started)
                    return
                key = hashlib.sha256((pipeline_version + digest).encode()).hexdigest()
                with Session() as session:
                    cached = session.get(DocumentCache, key)
                    stored = cached.passages if cached else None
                with timings.measure("document_parsing"):
                    if stored:
                        passages = [Passage(**item) for item in json.loads(stored)]
                    else:
                        _, passages = await read_source(kind, None, path)
                with timings.measure("chunking"):
                    chunks = await asyncio.to_thread(chunk_passages, passages)
                if not chunks:
                    raise ValueError("Document contains no readable text")
                with Session.begin() as session:
                    if stored is None:
                        with timings.measure("serialization"):
                            encoded = json.dumps(
                                [dict(text=p.text, reference=p.reference) for p in passages]
                            )
                        session.add(DocumentCache(id=key, passages=encoded))
                    existing = session.scalars(
                        select(Chunk).where(Chunk.source_id == source_id)
                    ).all()
                    affected = list(
                        session.scalars(
                            select(Mention.concept_id)
                            .join(Chunk)
                            .where(Chunk.source_id == source_id)
                            .distinct()
                        )
                    )
                    identities = {(c.text, c.reference): c.id for c in existing}
                    existing_ids = set(identities.values())
                    ids = []
                    for passage in chunks:
                        reference = json.dumps(passage.reference)
                        identifier = identities.get((passage.text, reference), str(uuid4()))
                        ids.append(identifier)
                        if identifier not in existing_ids:
                            session.add(
                                Chunk(
                                    id=identifier,
                                    source_id=source_id,
                                    text=passage.text,
                                    reference=reference,
                                    embedding="[]",
                                    embedding_model=settings.embedding_id,
                                )
                            )
                    retained = set(ids)
                    stale = [c.id for c in existing if c.id not in retained]
                    if stale:
                        session.execute(delete(Chunk).where(Chunk.id.in_(stale)))
                    # Replace only this document's graph when the extraction version changed.
                    if previous_version != pipeline_version:
                        for table in (Edge, EntitySpan, Mention):
                            session.execute(delete(table).where(table.chunk_id.in_(ids)))
                    session.flush()
                    prune_orphans(session)
                    rerank(session, affected)
                summary.update(
                    chunks=len(ids),
                    indexed_chunks=len(ids),
                    pages=len(passages),
                    graph_target_chunks=len(ids),
                    embedded_chunks=0,
                    document_cache_hit=stored is not None,
                    entity_engine=pipeline_version,
                )
                self.stage(job_id, "indexed")
                self.progress(job_id, summary, started)
                # Start with passages distributed across the document, then enrich all remaining text.
                count = min(settings.initial_graph_chunks, len(ids))
                first = list(
                    dict.fromkeys(
                        round(i * (len(ids) - 1) / max(count - 1, 1)) for i in range(count)
                    )
                )
                order = [ids[i] for i in first] + [
                    identifier for i, identifier in enumerate(ids) if i not in first
                ]
                batches = [order[:count]] + [
                    order[i : i + settings.extraction_batch_size]
                    for i in range(count, len(order), settings.extraction_batch_size)
                ]
                for index, batch in enumerate(batches):
                    hits, misses, added, connections = await asyncio.to_thread(
                        self.batch, batch, timings
                    )
                    summary["graph_chunks"] += len(batch)
                    summary["cache_hits"] += hits
                    summary["cache_misses"] += misses
                    summary["new_concepts"] += added
                    summary["new_connections"] += connections
                    summary["timings_ms"] = timings.values()
                    with Session.begin() as session:
                        session.get(Source, source_id).concept_count = session.scalar(
                            select(func.count(func.distinct(Mention.concept_id)))
                            .join(Chunk)
                            .where(Chunk.source_id == source_id)
                        )
                    if index == 0:
                        summary["initial_graph_ms"] = round(
                            (time.perf_counter() - started) * 1000, 3
                        )
                    self.stage(job_id, "enriching")
                    self.progress(job_id, summary, started)
                    await asyncio.sleep(0)
                with Session.begin() as session:
                    source = session.get(Source, source_id)
                    source.content_hash, source.pipeline_version = digest, pipeline_version
                    source.fingerprint, source.processed_at = key, now()
                self.stage(job_id, "completed")
                self.progress(job_id, summary, started)
            # Optional, sequential embeddings happen after graph publication, off the critical path.
            if settings.enable_embeddings:
                summary["embedding_status"] = "running"
                for chunk_id in ids:
                    with Session() as session:
                        chunk = session.get(Chunk, chunk_id)
                        if not chunk or chunk.embedding != "[]":
                            continue
                        text = chunk.text
                    with timings.measure("embedding_generation"):
                        vectors = await asyncio.wait_for(self.models.embed([text]), timeout=15)
                    with Session.begin() as session:
                        chunk = session.get(Chunk, chunk_id)
                        if chunk:
                            chunk.embedding = json.dumps(vectors[0])
                            chunk.embedding_model = settings.embedding_id
                    summary["embedded_chunks"] += 1
                    summary["timings_ms"] = timings.values()
                    self.progress(job_id, summary, started)
                summary["embedding_status"] = "completed"
                self.progress(job_id, summary, started)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            summary["timings_ms"] = timings.values()
            if summary.get("embedding_status") == "running":
                summary["embedding_status"] = f"unavailable: {error}"
            else:
                self.stage(job_id, "failed", str(error))
            self.progress(job_id, summary, started)
