export interface Source {
  id: string;
  kind: string;
  title: string;
  url: string | null;
  status: string;
  created_at: string;
  processed_at: string | null;
  error: string | null;
  concept_count: number;
}
export interface Node {
  id: string;
  name: string;
  description: string;
  domain: string;
  position: [number, number, number];
  created_at: string;
  source_ids: string[];
}
export interface Edge {
  id: string;
  source: string;
  target: string;
  relation: string;
  quote: string;
  confidence: number;
  kind?: string;
  verified?: boolean;
  method?: string;
}
export interface Graph {
  nodes: Node[];
  edges: Edge[];
  total_nodes?: number;
  limit?: number;
}
export interface Evidence {
  id?: string;
  quote?: string;
  text?: string;
  title: string;
  kind: string;
  source_id: string;
  url: string | null;
  reference: {
    url?: string;
    page?: number;
    timestamp?: number;
    path?: string;
    line_start?: number;
    line_end?: number;
    heading?: string;
  };
}
export interface Detail extends Node {
  evidence: Evidence[];
  relationships: Edge[];
  neighbor_names?: Record<string, string>;
}
export interface Reply {
  answer: string;
  citations: Evidence[];
  mode: string;
}
export interface Conversation extends Omit<Reply, "mode"> {
  id: string;
  question: string;
}
export interface Job {
  id: string;
  source_id: string;
  stage: string;
  error: string | null;
  elapsed_seconds: number;
  summary: {
    embedding_warning?: string;
    new_concepts?: number;
    new_connections?: number;
    chunks?: number;
    indexed_chunks?: number;
    embedded_chunks?: number;
    graph_chunks?: number;
    graph_target_chunks?: number;
    pages?: number;
    crawl_limited?: boolean;
    failed_pages?: number;
  };
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers:
      options?.body instanceof FormData
        ? undefined
        : { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Unable to reach Lumi" }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Please check the input and try again.",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function sourceLink(e: Evidence) {
  return (
    e.reference.url ||
    (["pdf", "docx", "txt"].includes(e.kind)
      ? `/api/sources/${e.source_id}/file${e.kind === "pdf" ? `#page=${e.reference.page || 1}` : ""}`
      : e.url || "#")
  );
}
