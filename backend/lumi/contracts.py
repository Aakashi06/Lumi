from typing import Literal

from pydantic import BaseModel, Field

Relation = Literal[
    "CO_OCCURS_WITH",
    "RELATED_TO",
    "PART_OF",
    "USES",
    "REQUIRES",
    "IMPLEMENTS",
    "EXTENDS",
    "COMPARES_WITH",
]


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)


class ExtractedConcept(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(max_length=1000)
    domain: str = Field(max_length=60)
    quote: str = Field(min_length=3)


class ExtractedEdge(BaseModel):
    source: str
    target: str
    relation: Relation
    quote: str = Field(min_length=3)
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    concepts: list[ExtractedConcept] = Field(max_length=25)
    relationships: list[ExtractedEdge] = Field(max_length=40)


class Answer(BaseModel):
    answer: str
    citation_ids: list[str]


class SourceResponse(BaseModel):
    id: str
    kind: Literal["pdf", "docx", "txt"]
    url: str | None
    title: str
    status: str
    created_at: str
    processed_at: str | None
    error: str | None
    concept_count: int


class IngestionResponse(BaseModel):
    source: SourceResponse
    job_id: str | None
    message: str | None = None


class JobResponse(BaseModel):
    id: str
    source_id: str
    stage: str
    error: str | None
    summary: dict
    elapsed_seconds: float


class NodeResponse(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    position: tuple[float, float, float]
    created_at: str
    source_ids: list[str] = Field(default_factory=list)
    importance: float = 0


class EdgeResponse(BaseModel):
    id: str
    source: str
    target: str
    relation: Relation
    chunk_id: str
    quote: str
    confidence: float
    kind: str = "semantic"
    verified: bool = False
    method: str = "legacy_llm"


class GraphResponse(BaseModel):
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]
    total_nodes: int = 0
    limit: int = 75


class EvidenceResponse(BaseModel):
    id: str | None = None
    source_id: str
    title: str
    kind: str
    url: str | None
    reference: dict
    text: str | None = None
    quote: str | None = None
    score: float | None = None


class ConceptResponse(NodeResponse):
    evidence: list[EvidenceResponse]
    relationships: list[EdgeResponse]
    neighbor_names: dict[str, str] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[EvidenceResponse]
    mode: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[EvidenceResponse]
    mode: str


class ConversationResponse(BaseModel):
    id: str
    question: str
    answer: str
    citations: list[EvidenceResponse]
    created_at: str
