"""Incremental NetworkX construction and indexed SQLite graph reads."""

import hashlib
import json
from uuid import uuid4

import networkx as nx
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.sqlite import insert

from .config import settings
from .db import Chunk, Concept, Edge, EntitySpan, Mention, Session, Source, serialize
from .graph import position

FILE_KINDS = ("pdf", "docx", "txt")


def identifier(*parts):
    return hashlib.sha256("\0".join(map(str, parts)).encode()).hexdigest()


def persist(session, chunk, result):
    graph = nx.MultiDiGraph()
    for hit in result["hits"]:
        graph.add_node(hit["key"], hit=hit)
    for edge in result["edges"]:
        graph.add_edge(
            edge["source"],
            edge["target"],
            **{key: value for key, value in edge.items() if key not in {"source", "target"}},
        )
    keys = list(graph.nodes)
    existing = {c.key: c for c in session.scalars(select(Concept).where(Concept.key.in_(keys)))}
    added = connections = 0
    for key, data in graph.nodes(data=True):
        if key not in existing:
            hit = data["hit"]
            concept = Concept(
                id=str(uuid4()),
                key=key,
                name=hit["name"],
                description=hit["quote"][:500],
                domain="Concepts",
                position=json.dumps(position(key, "Concepts")),
            )
            session.add(concept)
            existing[key] = concept
            added += 1
    session.flush()
    spans, mentions = [], {}
    for hit in result["hits"]:
        concept = existing[hit["key"]]
        spans.append(
            dict(
                id=identifier(concept.id, chunk.id, hit["start"], hit["end"]),
                concept_id=concept.id,
                chunk_id=chunk.id,
                start=hit["start"],
                end=hit["end"],
                text=hit["name"],
                label=hit["label"],
            )
        )
        mentions.setdefault(
            concept.id, dict(concept_id=concept.id, chunk_id=chunk.id, quote=hit["quote"])
        )
    if spans:
        session.execute(insert(EntitySpan).values(spans).on_conflict_do_nothing())
        session.execute(insert(Mention).values(list(mentions.values())).on_conflict_do_nothing())
    edges = []
    for a, b, data in graph.edges(data=True):
        source, target = existing[a].id, existing[b].id
        edges.append(
            dict(
                id=identifier(source, target, data["relation"], chunk.id, data["quote"]),
                source=source,
                target=target,
                chunk_id=chunk.id,
                **data,
            )
        )
    if edges:
        statement = insert(Edge).values(edges).on_conflict_do_nothing().returning(Edge.id)
        connections = len(session.execute(statement).all())
    rerank(session, [concept.id for concept in existing.values()])
    return added, connections


def rerank(session, ids):
    """Correct counts only for concepts affected by document replacement/deletion."""
    mentions = (
        select(func.count())
        .select_from(Mention)
        .where(Mention.concept_id == Concept.id)
        .correlate(Concept)
        .scalar_subquery()
    )
    statements = (
        select(func.count())
        .select_from(Edge)
        .where(or_(Edge.source == Concept.id, Edge.target == Concept.id), Edge.verified.is_(True))
        .correlate(Concept)
        .scalar_subquery()
    )
    session.execute(
        update(Concept).where(Concept.id.in_(ids)).values(importance=mentions + 2 * statements),
        execution_options={"synchronize_session": False},
    )


def node_rows(session, ids):
    provenance = {}
    for concept_id, source_id in session.execute(
        select(Mention.concept_id, Chunk.source_id)
        .join(Chunk)
        .join(Source)
        .where(Mention.concept_id.in_(ids), Source.kind.in_(FILE_KINDS))
        .distinct()
    ):
        provenance.setdefault(concept_id, []).append(source_id)
    return [
        dict(serialize(row), source_ids=provenance[row.id])
        for row in session.scalars(
            select(Concept)
            .where(Concept.id.in_(ids))
            .order_by(Concept.importance.desc(), Concept.id)
        )
        if row.id in provenance
    ]


def valid_concepts(source_id=None):
    statement = (
        select(Mention.concept_id)
        .join(Chunk)
        .join(Source)
        .where(Source.kind.in_(FILE_KINDS))
        .distinct()
    )
    return statement.where(Chunk.source_id == source_id) if source_id else statement


def read_graph(limit=None, expand=(), source_id=None):
    limit = max(1, min(limit or settings.graph_node_limit, 100))
    with Session() as session:
        ids = list(
            session.scalars(
                select(Concept.id)
                .where(Concept.id.in_(valid_concepts(source_id)))
                .order_by(Concept.importance.desc(), Concept.id)
                .limit(limit)
            )
        )
        expanded = list(expand)[:20]
        if expanded:
            adjacent = session.execute(
                select(Edge.source, Edge.target)
                .join(Chunk)
                .join(Source)
                .where(
                    Source.kind.in_(FILE_KINDS),
                    Chunk.source_id == source_id if source_id else True,
                    or_(Edge.source.in_(expanded), Edge.target.in_(expanded)),
                )
                .order_by(Edge.verified.desc(), Edge.confidence.desc(), Edge.id)
                .limit(400)
            ).all()
            ids = list(
                dict.fromkeys(expanded + ids + [node for pair in adjacent for node in pair])
            )[: settings.graph_expansion_limit]
        nodes = node_rows(session, ids)
        if source_id:
            nodes = [node for node in nodes if source_id in node["source_ids"]]
        ids = [node["id"] for node in nodes]
        representatives = (
            select(func.min(Edge.id))
            .join(Chunk)
            .join(Source)
            .where(
                Source.kind.in_(FILE_KINDS),
                Edge.source.in_(ids),
                Edge.target.in_(ids),
                Chunk.source_id == source_id if source_id else True,
            )
            .group_by(Edge.source, Edge.target, Edge.relation, Edge.kind, Edge.verified)
        )
        edges = [
            serialize(edge)
            for edge in session.scalars(
                select(Edge)
                .where(Edge.id.in_(representatives))
                .order_by(Edge.verified.desc(), Edge.confidence.desc(), Edge.id)
                .limit(600)
            )
        ]
        total = session.scalar(
            select(func.count())
            .select_from(Concept)
            .where(Concept.id.in_(valid_concepts(source_id)))
        )
        return dict(nodes=nodes, edges=edges, total_nodes=total, limit=limit)


def related_chunks(query):
    # These are retrieval hints only, never evidence replacing source passages.
    with Session() as session:
        ids = list(
            session.scalars(
                select(Concept.id)
                .where(
                    Concept.id.in_(valid_concepts()),
                    func.instr(query.casefold(), func.lower(Concept.name)) > 0,
                )
                .limit(100)
            )
        )
        return set(
            session.scalars(
                select(Edge.chunk_id)
                .where(or_(Edge.source.in_(ids), Edge.target.in_(ids)), Edge.verified.is_(True))
                .limit(100)
            )
        )
