import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import or_, select, text

from .config import settings
from .contracts import (
    ChatResponse,
    ConceptResponse,
    ConversationResponse,
    GraphResponse,
    IngestionResponse,
    JobResponse,
    NodeResponse,
    SearchInput,
    SearchResponse,
    SourceResponse,
)
from .db import (
    Concept,
    Edge,
    EntitySpan,
    Chunk,
    Conversation,
    Job,
    Mention,
    Session,
    Source,
    initialize_database,
    serialize,
)
from .graph import prune_orphans, review_comparisons
from .indexing import initialize_search
from .models import LocalModels
from .graph_store import FILE_KINDS, node_rows, read_graph, rerank
from .telemetry import TimedJSONResponse, snapshot
from .pipeline import Pipeline
from .retrieval import answer, search

models = LocalModels()
pipeline = Pipeline(models)
tasks: set[asyncio.Task] = set()


def launch(job_id):
    task = asyncio.create_task(pipeline.run(job_id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    initialize_search()
    resume = []
    with Session.begin() as session:
        review_comparisons(session)
        for job in session.scalars(select(Job).where(Job.stage.not_in(["completed", "failed"]))):
            job.stage, job.error = "queued", None
            source = session.get(Source, job.source_id)
            if source.kind not in FILE_KINDS:
                job.stage, source.status = "failed", "failed"
                job.error = source.error = (
                    "This source type is no longer supported. Upload a PDF, Word document, or text file."
                )
                continue
            source.status, source.error = "queued", None
            resume.append(job.id)
    for job_id in resume:
        launch(job_id)
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title="Lumi", version="0.1.0", lifespan=lifespan, default_response_class=TimedJSONResponse
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def get_or_404(session, cls, identifier):
    row = session.get(cls, identifier)
    if not row:
        raise HTTPException(404, "Not found")
    return row


def enqueue(session, source):
    source.status, source.error = "queued", None
    job = Job(id=str(uuid4()), source_id=source.id)
    session.add(job)
    session.commit()
    launch(job.id)
    return {"source": serialize(source), "job_id": job.id}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models": "local only",
        "graph_database": "SQLite / NetworkX",
        "generation_model": settings.model_id,
        "embedding_model": settings.embedding_id,
    }


@app.post("/api/sources/upload", status_code=202, response_model=IngestionResponse)
@app.post(
    "/api/sources/pdf", status_code=202, response_model=IngestionResponse, include_in_schema=False
)
async def add_file(file: UploadFile = File(...)):
    from io import BytesIO
    from zipfile import BadZipFile, ZipFile

    data = await file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds the 12 MB limit")
    name = Path(file.filename or "Document.pdf").name
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(422, "Upload PDF, Word (.docx), or UTF-8 text (.txt or .md).")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Upload a valid PDF file")
    if suffix == ".docx":
        try:
            with ZipFile(BytesIO(data)) as archive:
                if (
                    "word/document.xml" not in archive.namelist()
                    or sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024
                ):
                    raise ValueError()
        except (BadZipFile, ValueError):
            raise HTTPException(
                422, "Upload a valid Word (.docx) document under 50 MB uncompressed."
            )
    if suffix in {".txt", ".md"}:
        try:
            decoded = data.decode("utf-8-sig")
            if "\x00" in decoded:
                raise ValueError()
        except (UnicodeError, ValueError):
            raise HTTPException(422, "Upload a plain text file saved as UTF-8.")
    identifier = str(uuid4())
    folder = Path("data/uploads")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{identifier}{suffix}"
    path.write_bytes(data)
    with Session() as session:
        source = Source(
            id=identifier,
            kind="txt" if suffix == ".md" else suffix[1:],
            title=name,
            file_path=str(path.resolve()),
        )
        session.add(source)
        session.flush()
        return enqueue(session, source)


@app.get("/api/sources", response_model=list[SourceResponse])
def sources():
    with Session() as session:
        return [
            serialize(row)
            for row in session.scalars(
                select(Source).where(Source.kind.in_(FILE_KINDS)).order_by(Source.created_at.desc())
            )
        ]


@app.get("/api/sources/{identifier}", response_model=SourceResponse)
def source_detail(identifier: str):
    with Session() as session:
        return serialize(get_or_404(session, Source, identifier))


@app.get("/api/sources/{identifier}/file")
def source_file(identifier: str):
    with Session() as session:
        source = get_or_404(session, Source, identifier)
        if source.kind not in FILE_KINDS or not source.file_path:
            raise HTTPException(404, "No document available")
        return FileResponse(source.file_path, filename=source.title)


@app.post("/api/sources/{identifier}/retry", status_code=202, response_model=IngestionResponse)
async def retry(identifier: str):
    with Session() as session:
        source = get_or_404(session, Source, identifier)
        if source.status not in {"failed", "completed"}:
            raise HTTPException(409, "This resource is already processing")
        return enqueue(session, source)


@app.delete("/api/sources/{identifier}", status_code=204)
def remove(identifier: str):
    with Session.begin() as session:
        source = get_or_404(session, Source, identifier)
        if source.status not in {"failed", "completed"}:
            raise HTTPException(409, "Wait for processing to finish before deleting this resource")
        path = source.file_path
        affected = list(
            session.scalars(
                select(Mention.concept_id)
                .join(Chunk)
                .where(Chunk.source_id == identifier)
                .distinct()
            )
        )
        # Saved answers containing this source cannot retain deleted evidence.
        for conversation in session.scalars(select(Conversation)):
            if any(
                citation["source_id"] == identifier
                for citation in json.loads(conversation.citations)
            ):
                session.delete(conversation)
        session.delete(source)
        session.flush()
        prune_orphans(session)
        rerank(session, affected)
    if path:
        Path(path).unlink(missing_ok=True)


@app.get("/api/jobs/{identifier}", response_model=JobResponse)
def job(identifier: str):
    with Session() as session:
        return serialize(get_or_404(session, Job, identifier))


@app.get("/api/jobs", response_model=list[JobResponse])
def jobs():
    with Session() as session:
        return [
            serialize(row)
            for row in session.scalars(
                select(Job)
                .join(Source)
                .where(Source.kind.in_(FILE_KINDS))
                .order_by(text("jobs.rowid"))
            )
        ]


@app.get("/api/performance")
def performance():
    return {"samples": snapshot(), "embedding_enabled": settings.enable_embeddings}


@app.get("/api/graph", response_model=GraphResponse)
def graph(limit: int = 75, expand: str = "", source_id: str | None = None):
    return read_graph(limit, expand.split(",") if expand else (), source_id)


@app.get("/api/graph/concepts/{identifier}", response_model=ConceptResponse)
def concept(identifier: str):
    with Session() as session:
        nodes = node_rows(session, [identifier])
        if not nodes:
            raise HTTPException(404, "Concept not found")
        node = nodes[0]
        mentions = session.execute(
            select(Mention, Chunk, Source)
            .join(Chunk, Mention.chunk_id == Chunk.id)
            .join(Source, Chunk.source_id == Source.id)
            .where(Mention.concept_id == identifier, Source.kind.in_(FILE_KINDS))
            .limit(32)
        ).all()
        spans = session.scalars(
            select(EntitySpan).where(
                EntitySpan.concept_id == identifier,
                EntitySpan.chunk_id.in_([chunk.id for _, chunk, _ in mentions]),
            )
        ).all()
        by_chunk = {}
        for span in spans:
            by_chunk.setdefault(span.chunk_id, []).append(span)
        node["evidence"] = []
        for mention, chunk, source in mentions:
            reference = json.loads(chunk.reference)
            reference["entity_spans"] = [
                {
                    "start": span.start + reference.get("char_start", 0),
                    "end": span.end + reference.get("char_start", 0),
                    "text": span.text,
                    "label": span.label,
                }
                for span in by_chunk.get(chunk.id, [])
            ]
            node["evidence"].append(
                dict(
                    quote=mention.quote,
                    source_id=source.id,
                    title=source.title,
                    kind=source.kind,
                    url=source.url,
                    reference=reference,
                )
            )
        edges = session.scalars(
            select(Edge)
            .join(Chunk)
            .join(Source)
            .where(
                Source.kind.in_(FILE_KINDS),
                or_(Edge.source == identifier, Edge.target == identifier),
            )
            .order_by(Edge.verified.desc(), Edge.id)
            .limit(100)
        ).all()
        node["relationships"] = [serialize(edge) for edge in edges]
        ids = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
        node["neighbor_names"] = dict(
            session.execute(select(Concept.id, Concept.name).where(Concept.id.in_(ids))).all()
        )
        return node


@app.get("/api/graph/concepts/{identifier}/neighbors", response_model=list[NodeResponse])
def neighbors(identifier: str):
    with Session() as session:
        pairs = session.execute(
            select(Edge.source, Edge.target)
            .where(or_(Edge.source == identifier, Edge.target == identifier))
            .limit(100)
        ).all()
        return node_rows(
            session, {endpoint for pair in pairs for endpoint in pair if endpoint != identifier}
        )


@app.post("/api/search", response_model=SearchResponse)
async def query(body: SearchInput):
    evidence, mode = await search(body.query, body.limit, models)
    return {"results": evidence, "mode": mode}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: SearchInput):
    try:
        result = await answer(body.query, models)
    except Exception as error:
        raise HTTPException(
            503, f"Local generation failed: {error}. Check your Qwen server and retry."
        ) from error
    with Session.begin() as session:
        session.add(
            Conversation(
                id=str(uuid4()),
                question=body.query,
                answer=result["answer"],
                citations=json.dumps(result["citations"]),
            )
        )
    return result


@app.get("/api/chat", response_model=list[ConversationResponse])
def history():
    with Session() as session:
        allowed = set(session.scalars(select(Source.id).where(Source.kind.in_(FILE_KINDS))))
        return [
            serialize(row)
            for row in session.scalars(
                select(Conversation).order_by(Conversation.created_at).limit(100)
            )
            if all(item["source_id"] in allowed for item in json.loads(row.citations))
        ]
