import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import ForeignKey, Index, String, Text, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    url: Mapped[str | None]
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    created_at: Mapped[str] = mapped_column(default=now)
    processed_at: Mapped[str | None]
    fingerprint: Mapped[str | None]
    content_hash: Mapped[str | None]
    pipeline_version: Mapped[str | None]
    file_path: Mapped[str | None]
    error: Mapped[str | None] = mapped_column(Text)
    concept_count: Mapped[int] = mapped_column(default=0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(default="{}")
    elapsed_seconds: Mapped[float] = mapped_column(default=0)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str]


class Concept(Base):
    __tablename__ = "concepts"
    id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(Text)
    domain: Mapped[str]
    position: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)
    importance: Mapped[float] = mapped_column(default=0.0)


class Mention(Base):
    __tablename__ = "mentions"
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    quote: Mapped[str] = mapped_column(Text)


class Edge(Base):
    __tablename__ = "edges"
    id: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(ForeignKey("concepts.id", ondelete="CASCADE"))
    target: Mapped[str] = mapped_column(ForeignKey("concepts.id", ondelete="CASCADE"))
    relation: Mapped[str]
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    quote: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float]
    kind: Mapped[str] = mapped_column(default="semantic")
    verified: Mapped[bool] = mapped_column(default=False)
    method: Mapped[str] = mapped_column(default="legacy_llm")


class EntitySpan(Base):
    __tablename__ = "entity_spans"
    id: Mapped[str] = mapped_column(primary_key=True)
    concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    start: Mapped[int]
    end: Mapped[int]
    text: Mapped[str]
    label: Mapped[str]


class DocumentCache(Base):
    __tablename__ = "document_cache"
    id: Mapped[str] = mapped_column(primary_key=True)
    passages: Mapped[str] = mapped_column(Text)


class ExtractionCache(Base):
    __tablename__ = "extraction_cache"
    id: Mapped[str] = mapped_column(primary_key=True)
    result: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(default=now)


if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def sqlite_setup(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")


Index("ix_concepts_importance", Concept.importance)
Index("ix_edges_source", Edge.source)
Index("ix_edges_target", Edge.target)
Index("ix_edges_chunk", Edge.chunk_id)
Index("ix_mentions_chunk", Mention.chunk_id)


def initialize_database():
    """Additive migration: keep existing documents, evidence, and conversations."""
    additions = {
        "sources": {"content_hash": "TEXT", "pipeline_version": "TEXT"},
        "concepts": {"importance": "FLOAT NOT NULL DEFAULT 0"},
        "edges": {
            "kind": "TEXT NOT NULL DEFAULT 'semantic'",
            "verified": "BOOLEAN NOT NULL DEFAULT 0",
            "method": "TEXT NOT NULL DEFAULT 'legacy_llm'",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        for table, columns in additions.items():
            if table not in existing:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in present:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
    Base.metadata.create_all(engine)
    for table in (Concept.__table__, Edge.__table__, Mention.__table__):
        for index in table.indexes:
            index.create(engine, checkfirst=True)


Session = sessionmaker(engine, expire_on_commit=False)


def serialize(row):
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for name in ("position", "reference", "summary", "citations"):
        if name in result:
            result[name] = json.loads(result[name])
    return result
