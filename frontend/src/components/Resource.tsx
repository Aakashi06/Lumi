import { FileText, ArrowUpRight, Check, X, LoaderCircle } from "lucide-react";
import type { Source, Job } from "../api";
const date = (value: string) =>
  new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

export default function Resource({
  source: s,
  onRetry,
  onViewGraph,
  job,
}: {
  source: Source;
  onRetry: () => void;
  onViewGraph: () => void;
  job?: Job;
}) {
  return (
    <article className="resource">
      <div className={`resource-icon ${s.kind}`}>
        <FileText size={20} />
      </div>
      <div className="resource-info">
        <div className="resource-type">
          {s.kind === "docx" ? "WORD" : s.kind === "txt" ? "TEXT" : "PDF"}
          <span>·</span>
          {date(s.created_at)}
        </div>
        <a href={`/api/sources/${s.id}/file`} target="_blank" rel="noreferrer">
          <strong>{s.title.split(" | ")[0]}</strong>
          <ArrowUpRight size={14} />
        </a>
        <div className={`resource-status ${s.status}`}>
          <span>
            {s.status === "completed" ? (
              <Check size={12} />
            ) : s.status === "failed" ? (
              <X size={12} />
            ) : (
              <LoaderCircle className="spin" size={12} />
            )}
            {s.status === "completed"
              ? `${s.concept_count} concepts indexed`
              : s.status === "enriching"
                ? "Graph ready · adding connections"
                : s.status === "queued"
                  ? "Waiting to process"
                  : s.status === "indexed"
                    ? "Text ready · mapping concepts"
                    : "Reading document"}
          </span>
          {s.status === "failed" && <button onClick={onRetry}>Retry</button>}
        </div>
        {job?.summary.indexed_chunks && (
          <div className="index-coverage">
            {job.summary.pages || 1} pages · {job.summary.indexed_chunks}{" "}
            passages searchable
            {job.summary.crawl_limited ? " · crawl limit reached" : ""}
            {!!job.summary.failed_pages &&
              ` · ${job.summary.failed_pages} pages unavailable`}
            {s.status === "completed" &&
              job.summary.graph_chunks !== undefined && (
                <span>
                  {job.summary.graph_chunks} sections mapped to the graph
                </span>
              )}
            {s.status !== "completed" && (
              <span>
                Mapping {job.summary.graph_chunks || 0}/
                {job.summary.graph_target_chunks || "…"} sections
              </span>
            )}
          </div>
        )}
        {job?.summary.embedding_warning && (
          <p className="index-coverage">{job.summary.embedding_warning}</p>
        )}
        {(s.concept_count > 0 || s.status === "completed") && (
          <button className="text-action" onClick={onViewGraph}>
            Open graph <ArrowUpRight size={14} />
          </button>
        )}
        {s.error && <p className="error">{s.error}</p>}
        {s.processed_at && (
          <small className="processed-date">
            Last processed {date(s.processed_at)}
          </small>
        )}
      </div>
    </article>
  );
}
