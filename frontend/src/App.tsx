import { Profiler, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Plus, ArrowUpRight, X, LoaderCircle, Orbit } from "lucide-react";
import { api, type Source, type Graph, type Detail, type Job } from "./api";
import Dashboard from "./pages/Dashboard";
import LibraryPage from "./pages/LibraryPage";
import ChatPage from "./pages/ChatPage";
import AddKnowledge from "./components/AddKnowledge";
import Citation from "./components/Citation";
import { recordMetric } from "./performance";

export default function App() {
  const client = useQueryClient();
  const [page, setPage] = useState("home");
  const [add, setAdd] = useState(false);
  const [submitted, setSubmitted] = useState<Source | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [sourceScope, setSourceScope] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<Source[]>("/sources"),
    refetchInterval: 4000,
  });
  const sources = sourcesQuery.data || [];
  const latest = submitted || sources[0];
  const notice =
    latest && latest.id !== dismissed
      ? sources.find((source) => source.id === latest.id) || latest
      : null;
  const processing = sources.some(
    (s) => !["completed", "failed"].includes(s.status),
  );
  const graphQuery = useQuery({
    queryKey: ["graph", expanded, sourceScope],
    queryFn: () =>
      api<Graph>(
        `/graph?limit=75&expand=${expanded.join(",")}${sourceScope ? `&source_id=${sourceScope}` : ""}`,
      ),
    refetchInterval: processing && page === "universe" ? 1000 : false,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<Job[]>("/jobs"),
    refetchInterval: processing ? 2500 : false,
  });
  const noticeJob = jobsQuery.data
    ?.filter((job) => job.source_id === notice?.id)
    .at(-1);
  const detail = useQuery({
    queryKey: ["concept", selected],
    queryFn: () => api<Detail>(`/graph/concepts/${selected}`),
    enabled: !!selected,
  });
  const graph = graphQuery.data || { nodes: [], edges: [] };
  const sourceVersion = sources
    .map((s) => `${s.id}:${s.status}:${s.concept_count}`)
    .join("|");
  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
  }, []);
  useEffect(() => {
    client.invalidateQueries({ queryKey: ["graph"] });
    client.invalidateQueries({ queryKey: ["concept"] });
  }, [sourceVersion, client]);
  const connections =
    detail.data?.relationships.filter(
      (edge, index, edges) =>
        edges.findIndex(
          (other) =>
            other.source === edge.source &&
            other.target === edge.target &&
            other.relation === edge.relation,
        ) === index,
    ) || [];
  const evidence =
    detail.data?.evidence.filter(
      (item, index, items) =>
        items.findIndex(
          (other) =>
            other.source_id === item.source_id &&
            other.reference.url === item.reference.url &&
            other.reference.page === item.reference.page &&
            other.quote === item.quote,
        ) === index,
    ) || [];
  const relationshipLabel = (type: string, outbound: boolean) => {
    const labels: Record<string, [string, string]> = {
      CO_OCCURS_WITH: [
        "appears in the same sentence as",
        "appears in the same sentence as",
      ],
      RELATED_TO: ["related to", "related to"],
      PART_OF: ["part of", "contains"],
      USES: ["uses", "used by"],
      REQUIRES: ["requires", "required by"],
      IMPLEMENTS: ["implements", "implemented by"],
      EXTENDS: ["extends", "extended by"],
      COMPARES_WITH: ["compares with", "compares with"],
    };
    return labels[type]?.[outbound ? 0 : 1] || type.toLowerCase();
  };
  const ask = (text: string) => {
    setQuestion(text);
    setSelected(null);
    setPage("chat");
  };

  return (
    <div className="lumi-shell">
      <header className="navigation glass">
        <button
          className="wordmark"
          aria-label="Lumi home"
          onClick={() => setPage("home")}
        >
          <Orbit size={23} />
          lumi
        </button>

        <div className="header-actions">
          <button className="primary" onClick={() => setAdd(true)}>
            <Plus size={16} />
            <span>Add source</span>
          </button>
        </div>
      </header>
      <nav className="primary-nav" aria-label="Main navigation">
        {[
          ["home", "Home"],
          ["universe", "Graph"],
          ["library", "Library"],
          ["chat", "Ask Lumi"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={page === id ? "current" : ""}
            onClick={() => setPage(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      {sourcesQuery.error && (
        <div className="connection-error" role="alert">
          Backend unavailable.{" "}
          <button onClick={() => sourcesQuery.refetch()}>Reconnect</button>
        </div>
      )}
      {graphQuery.error && page === "universe" && (
        <div className="connection-error" role="alert">
          {graphQuery.error.message}{" "}
          <button onClick={() => graphQuery.refetch()}>Retry graph</button>
        </div>
      )}
      {notice && (page === "universe" || page === "library") && (
        <aside className="source-notice glass" role="status" aria-live="polite">
          <div className="source-notice-body">
            {!["completed", "failed"].includes(notice.status) && (
              <LoaderCircle size={16} className="spin" />
            )}
            <div>
              <strong>
                {notice.status === "failed"
                  ? "Source needs attention"
                  : notice.status === "completed"
                    ? "Source processed"
                    : notice.status === "queued"
                      ? "Source added · waiting to process"
                      : notice.status === "enriching"
                        ? "Graph ready · enriching connections…"
                        : "Processing your source…"}
              </strong>
              <p>
                {notice.status === "failed"
                  ? notice.error
                  : notice.status === "completed"
                    ? `${notice.title} · ${notice.concept_count ? `${notice.concept_count} graph concepts` : "Searchable text saved; no graph concepts found."}`
                    : `${notice.title} · ${noticeJob?.summary.graph_target_chunks ? `${noticeJob.summary.graph_chunks || 0}/${noticeJob.summary.graph_target_chunks} passages mapped` : notice.status === "queued" ? "Waiting to read" : "Reading text"}`}
              </p>
            </div>
          </div>
          <div className="source-notice-actions">
            <button className="text-action" onClick={() => setPage("library")}>
              View source <ArrowUpRight size={14} />
            </button>
            <button
              className="icon-button"
              aria-label="Dismiss source status"
              onClick={() => setDismissed(notice.id)}
            >
              <X size={16} />
            </button>
          </div>
        </aside>
      )}
      <AnimatePresence mode="wait">
        <motion.main
          key={page}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
        >
          {(page === "universe" || page === "home") && (
            <Profiler
              id="graph-dashboard"
              onRender={(_, phase, duration) =>
                recordMetric(`frontend_render_${phase}`, duration)
              }
            >
              <Dashboard
                landing={page === "home"}
                onStart={() => setAdd(true)}
                graph={graph}
                sourceScope={sourceScope}
                onSourceChange={(id) => {
                  setSourceScope(id);
                  setExpanded([]);
                  setSelected(null);
                }}
                sources={sources}
                jobs={jobsQuery.data || []}
                selected={selected}
                onSelect={setSelected}
                onAsk={ask}
                onOpenSources={() => setPage("library")}
                onAdd={() => setAdd(true)}
              />
            </Profiler>
          )}
          {page === "library" && (
            <section className="reading-page">
              <div className="page-title">
                <span className="kicker">Your collection</span>
                <h1>Knowledge, kept.</h1>
              </div>
              <LibraryPage
                sources={sources}
                onAdd={() => setAdd(true)}
                onDeleted={() => {
                  setSelected(null);
                  setSourceScope(null);
                }}
                onViewGraph={(id) => {
                  setSourceScope(id);
                  setExpanded([]);
                  setPage("universe");
                }}
                jobs={jobsQuery.data || []}
              />
            </section>
          )}
          {page === "chat" && (
            <ChatPage question={question} setQuestion={setQuestion} />
          )}
        </motion.main>
      </AnimatePresence>
      <AnimatePresence>
        {add && (
          <AddKnowledge
            close={() => setAdd(false)}
            onSubmitted={(source) => {
              setPage("universe");
              setSubmitted(source);
              setSourceScope(source.id);
              setExpanded([]);
              setSelected(null);
              setDismissed(null);
            }}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {selected && (
          <motion.aside
            className="detail-panel glass"
            initial={{ x: 420, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ type: "spring", stiffness: 280, damping: 32 }}
          >
            <div className="detail-header">
              <span className="kicker">Connected thought</span>
              <button
                className="icon-button"
                onClick={() => setSelected(null)}
                aria-label="Close concept"
              >
                <X size={19} />
              </button>
            </div>
            {detail.data ? (
              <>
                <span className="detail-domain">{detail.data.domain}</span>
                <h2>{detail.data.name}</h2>
                <p>{detail.data.description}</p>
                <button
                  className="primary"
                  onClick={() =>
                    ask(`Explain ${detail.data!.name} using my sources.`)
                  }
                >
                  Explore with Lumi <ArrowUpRight size={15} />
                </button>
                <button
                  className="text-action"
                  onClick={() => {
                    setExpanded((ids) =>
                      [...new Set([selected!, ...ids])].slice(0, 20),
                    );
                    setPage("universe");
                  }}
                >
                  Show connections in graph <ArrowUpRight size={15} />
                </button>
                <h3>Connections</h3>
                {connections.map((e) => (
                  <button
                    className="relationship"
                    key={e.id}
                    onClick={() =>
                      setSelected(e.source === selected ? e.target : e.source)
                    }
                  >
                    <strong>
                      {graph.nodes.find(
                        (n) =>
                          n.id ===
                          (e.source === selected ? e.target : e.source),
                      )?.name ||
                        detail.data?.neighbor_names?.[
                          e.source === selected ? e.target : e.source
                        ] ||
                        "Related concept"}
                    </strong>
                    <small>
                      {relationshipLabel(e.relation, e.source === selected)}
                      {e.kind === "cooccurrence"
                        ? " · co-occurrence"
                        : e.verified
                          ? " · stated in source"
                          : " · unverified"}
                    </small>
                  </button>
                ))}
                <h3>Sources</h3>
                {evidence.map((e, index) => (
                  <Citation key={index} evidence={e} />
                ))}
              </>
            ) : detail.error ? (
              <p className="error">{detail.error.message}</p>
            ) : (
              <LoaderCircle className="spin" size={18} />
            )}
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
