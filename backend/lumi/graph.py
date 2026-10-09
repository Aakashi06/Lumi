"""Conservative entity resolution and evidence-backed graph persistence."""

import hashlib
import math
import re

from sqlalchemy import delete, select

from .contracts import Extraction
from .db import Concept, Edge, Mention


def normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.casefold().strip())


def position(key: str, domain: str) -> list[float]:
    seed = hashlib.sha256(key.encode()).digest()
    cluster = int.from_bytes(hashlib.sha256(domain.casefold().encode()).digest()[:2], "big") % 8
    angle = cluster * math.tau / 8
    return [
        round(math.cos(angle) * 5 + (seed[0] / 255 - 0.5) * 5, 3),
        round((seed[1] / 255 - 0.5) * 7, 3),
        round(math.sin(angle) * 5 + (seed[2] / 255 - 0.5) * 5, 3),
    ]


def comparison_supported(quote: str) -> bool:
    return bool(
        re.search(
            r"\b(?:compar\w*|contrast\w*|versus|vs|unlike|whereas|difference\w*)\b", quote, re.I
        )
    )


def review_comparisons(session):
    # Exact quotes do not by themselves establish a comparison relationship.
    for edge in session.scalars(
        select(Edge).where(Edge.relation == "COMPARES_WITH", Edge.confidence >= 0.75)
    ):
        if not comparison_supported(edge.quote):
            edge.confidence = 0.65


def verify_extraction(text: str, extraction: Extraction) -> Extraction:
    """Normalize only whitespace introduced by parsers; never accept paraphrased evidence."""
    names = {normalize(item.name) for item in extraction.concepts}
    for item in [*extraction.concepts, *extraction.relationships]:
        pattern = r"\s+".join(re.escape(part) for part in item.quote.split())
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"Quote must be one contiguous source excerpt: {item.quote!r}")
        item.quote = match.group(0)
    for edge in extraction.relationships:
        if normalize(edge.source) not in names or normalize(edge.target) not in names:
            raise ValueError("Relationship endpoints must name concepts in this extraction")
        if edge.relation == "COMPARES_WITH" and not comparison_supported(edge.quote):
            edge.confidence = min(edge.confidence, 0.65)
        if normalize(edge.source) == normalize(edge.target):
            raise ValueError("A relationship needs two distinct concepts")
    return extraction


def prune_orphans(session):
    session.execute(delete(Concept).where(~Concept.id.in_(select(Mention.concept_id))))
