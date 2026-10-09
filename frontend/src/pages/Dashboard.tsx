import {
  Component,
  lazy,
  Suspense,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useReducedMotion } from "motion/react";
import {
  ArrowUp,
  ArrowUpRight,
  Search,
  SlidersHorizontal,
  List,
  Box,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { Graph, Source, Node, Job } from "../api";
import { usePreferences } from "../store";
import TypewriterHeading from "../components/TypewriterHeading";
const Universe = lazy(() => import("../Universe"));

class SceneBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
interface Props {
  landing: boolean;
  onStart: () => void;
  graph: Graph;
  sourceScope: string | null;
  onSourceChange: (id: string | null) => void;
  sources: Source[];
  jobs: Job[];
  selected: string | null;
  onSelect: (id: string) => void;
  onAsk: (question: string) => void;
  onAdd: () => void;
  onOpenSources: () => void;
}

export default function Dashboard({
  landing,
  onStart,
  graph,
  sourceScope,
  onSourceChange,
  sources,
  jobs,
  selected,
  onSelect,
  onAsk,
  onAdd,
  onOpenSources,
}: Props) {
  const { performance, togglePerformance } = usePreferences();
  const reduced = useReducedMotion();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState(false);
  const [domain, setDomain] = useState("All topics");
  const source = sourceScope || "All sources";
  const setSource = (id: string) =>
    onSourceChange(id === "All sources" ? null : id);
  const [focus, setFocus] = useState<Node>();
  const [reset, setReset] = useState(0);
  const [zoom, setZoom] = useState({ step: 0, direction: 1 });

  // Source nodes keep the dashboard useful before concept extraction finishes.
  const sourceNodes: Node[] = sources.slice(0, 20).map((item, index) => ({
    id: `source:${item.id}`,
    name: item.title,
    description: item.status,
    domain: "Sources",
    position: [
      Math.cos(index * 2.4) * (sources.length > 1 ? 3 : 0),
      Math.sin(index * 2.4) * 3,
      -2,
    ],
    created_at: item.created_at,
    source_ids: [item.id],
  }));
  const dashboardGraph: Graph = {
    nodes: [...sourceNodes, ...graph.nodes],
    edges: [
      ...graph.edges,
      ...graph.nodes.flatMap((node) =>
        node.source_ids
          .filter((id) =>
            sourceNodes.some((item) => item.id === `source:${id}`),
          )
          .map((id) => ({
            id: `source:${id}:${node.id}`,
            source: `source:${id}`,
            target: node.id,
            relation: "CONTAINS",
            quote: "",
            confidence: 1,
            kind: "provenance",
            verified: true,
            method: "document_source",
          })),
      ),
    ],
  };
  const openNode = (id: string) =>
    id.startsWith("source:") ? onOpenSources() : onSelect(id);
  const domains = useMemo(
    () => [...new Set(dashboardGraph.nodes.map((n) => n.domain))].sort(),
    [graph.nodes, sources],
  );
  const nodes = dashboardGraph.nodes.filter(
    (n) =>
      (domain === "All topics" || domain === n.domain) &&
      (source === "All sources" || n.source_ids.includes(source)),
  );
  const ids = new Set(nodes.map((n) => n.id));
  const filtered = {
    nodes,
    edges: dashboardGraph.edges.filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    ),
  };
  const matches = query.trim()
    ? nodes
        .filter((n) => n.name.toLowerCase().includes(query.toLowerCase()))
        .slice(0, 5)
    : [];
  const processing = sources.find(
    (s) => !["completed", "failed"].includes(s.status),
  );
  const job = jobs.filter((j) => j.source_id === processing?.id).at(-1);
  const select = (node: Node) => {
    openNode(node.id);
    setFocus(node);
    setQuery("");
  };
  const fallback = (
    <div className="concept-list">
      {nodes.map((n) => (
        <button key={n.id} onClick={() => select(n)}>
          <span className="concept-dot" />
          <strong>{n.name}</strong>
          <small>{n.domain}</small>
          <ArrowUpRight size={15} />
        </button>
      ))}
      {!nodes.length && (
        <button className="empty-list" onClick={onAdd}>
          Add your first source <ArrowUpRight size={17} />
        </button>
      )}
    </div>
  );

  return (
    <section
      className={`universe-page ${landing ? "landing-page" : "graph-dashboard"}`}
    >
      <div className="scene-wrap">
        <SceneBoundary fallback={fallback}>
          {performance ? (
            fallback
          ) : (
            <Suspense
              fallback={
                <div className="scene-loading">Opening your universe</div>
              }
            >
              <Universe
                graph={landing ? { nodes: [], edges: [] } : filtered}
                selected={selected}
                onSelect={openNode}
                focus={focus}
                onFocus={setFocus}
                reset={reset}
                zoom={zoom}
                landing={landing}
                light={false}
                reducedMotion={!!reduced}
              />
            </Suspense>
          )}
        </SceneBoundary>
      </div>
      {landing ? (
        <div className="universe-copy">
          <span className="kicker">A universe of your own</span>
          <TypewriterHeading />
          <p>Save a source. Follow an idea.</p>
          <button className="text-action" onClick={onStart}>
            Make your knowledge graph <ArrowUpRight size={17} />
          </button>
        </div>
      ) : (
        <div className="dashboard-title">
          <span className="kicker">Your workspace</span>
          <h1>Knowledge graph.</h1>
          <p>
            {graph.nodes.length} of {graph.total_nodes ?? graph.nodes.length}{" "}
            concepts · {sources.length}{" "}
            {sources.length === 1 ? "source" : "sources"}
          </p>
        </div>
      )}
      {!landing && sources.length > 0 && (
        <aside className="graph-sources glass" aria-label="Graph sources">
          <span className="kicker">Sources</span>
          {sources.slice(0, 5).map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setFocus(
                  sourceNodes.find((node) => node.id === `source:${item.id}`),
                );
              }}
            >
              <strong>{item.title}</strong>
              <small>
                {item.status === "completed" ? "Ready" : item.status}
              </small>
            </button>
          ))}
          <button className="text-action" onClick={onAdd}>
            Add source <ArrowUpRight size={14} />
          </button>
        </aside>
      )}
      {!landing && !sources.length && (
        <div className="graph-empty glass">
          <h2>Your graph starts here.</h2>
          <p>Upload a PDF, Word document, or text file.</p>
          <button className="primary" onClick={onAdd}>
            Add your first source <ArrowUpRight size={16} />
          </button>
        </div>
      )}
      {!landing && (
        <div className="scene-actions glass">
          <button
            className="icon-button"
            aria-label="Zoom in"
            title="Zoom in"
            onClick={() =>
              setZoom((value) => ({ step: value.step + 1, direction: 1 }))
            }
          >
            <ZoomIn size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Zoom out"
            title="Zoom out"
            onClick={() =>
              setZoom((value) => ({ step: value.step + 1, direction: -1 }))
            }
          >
            <ZoomOut size={17} />
          </button>
          <button
            className="icon-button"
            title="Filters"
            onClick={() => setFilters(!filters)}
          >
            <SlidersHorizontal size={17} />
          </button>
          <button
            className="icon-button"
            title="Reset camera"
            onClick={() => {
              setFocus(undefined);
              setReset((v) => v + 1);
            }}
          >
            <RotateCcw size={17} />
          </button>
          <button
            className="icon-button"
            title="Toggle accessible list"
            onClick={togglePerformance}
          >
            {performance ? <Box size={17} /> : <List size={17} />}
          </button>
        </div>
      )}
      {filters && !landing && (
        <div className="filter-popover glass">
          <label>
            Topic
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option>All topics</option>
              {domains.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label>
            Source
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option>All sources</option>
              {sources.map((s) => (
                <option value={s.id} key={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <div className="universe-command">
        <form
          className="command-input glass"
          onSubmit={(e) => {
            e.preventDefault();
            if (matches[0]) select(matches[0]);
            else if (query.trim()) onAsk(query);
          }}
        >
          <Search size={17} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a thought, or ask a question"
            aria-label="Find a concept or ask Lumi"
          />
          <button aria-label="Explore" disabled={!query.trim()}>
            <ArrowUp size={17} />
          </button>
        </form>
        {matches.length > 0 && (
          <div className="command-results glass">
            {matches.map((n) => (
              <button key={n.id} onClick={() => select(n)}>
                {n.name}
                <ArrowUpRight size={15} />
              </button>
            ))}
          </div>
        )}
      </div>
      <footer className="universe-footer">
        <span>
          {processing ? (
            <>
              <i className="activity-dot" />
              {job?.summary.indexed_chunks
                ? `Search ready · ${job.summary.graph_chunks || 0}/${job.summary.graph_target_chunks || "…"} mapped`
                : "Reading your source"}
            </>
          ) : (
            <>
              <i className="activity-dot quiet" />
              {graph.nodes.length} thoughts · {sources.length}{" "}
              {sources.length === 1 ? "source" : "sources"}
            </>
          )}
        </span>
        <span className="orbit-hint">
          Scroll to zoom · Drag to orbit · Select a node
        </span>
      </footer>
    </section>
  );
}
