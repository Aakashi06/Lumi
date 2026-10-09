import { ArrowUpRight } from "lucide-react";
import { sourceLink, type Evidence } from "../api";

export default function Citation({
  evidence,
  number,
}: {
  evidence: Evidence;
  number?: number;
}) {
  const r = evidence.reference;
  const label =
    r.heading || (r.page ? `Page ${r.page}` : r.path || evidence.title);
  const host = evidence.url ? new URL(evidence.url).hostname : evidence.title;
  return (
    <div className="citation">
      <a href={sourceLink(evidence)} target="_blank" rel="noreferrer">
        <span className="citation-index">{number || "↗"}</span>
        <div>
          <strong>{label}</strong>
          <small>
            {host}
            {r.timestamp !== undefined
              ? ` · ${Math.floor(r.timestamp / 60)}:${String(Math.floor(r.timestamp % 60)).padStart(2, "0")}`
              : ""}
          </small>
        </div>
        <ArrowUpRight size={16} />
      </a>
      <details>
        <summary>View passage</summary>
        <p>{evidence.quote || evidence.text}</p>
      </details>
    </div>
  );
}
