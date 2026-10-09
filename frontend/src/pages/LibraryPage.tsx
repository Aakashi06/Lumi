import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, RotateCcw, Trash2, Library, Plus } from "lucide-react";
import { api, type Source, type Job } from "../api";
import Resource from "../components/Resource";
const active = (status: string) => !["completed", "failed"].includes(status);
const kinds = ["pdf", "docx", "txt"];
interface Props {
  sources: Source[];
  onAdd: () => void;
  onDeleted: () => void;
  onViewGraph: (id: string) => void;
  jobs: Job[];
}
export default function LibraryPage({
  sources,
  onAdd,
  onDeleted,
  onViewGraph,
  jobs,
}: Props) {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("All sources");
  const remove = useMutation({
    mutationFn: (id: string) => api(`/sources/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      onDeleted();
      client.invalidateQueries({ queryKey: ["history"] });
      client.invalidateQueries({ queryKey: ["sources"] });
      client.invalidateQueries({ queryKey: ["graph"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const retry = useMutation({
    mutationFn: (id: string) => api(`/sources/${id}/retry`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["sources"] }),
  });
  const librarySources = sources.filter(
    (s) =>
      s.title.toLowerCase().includes(query.toLowerCase()) &&
      (sourceFilter === "All sources" || s.kind === sourceFilter),
  );
  return (
    <>
      <div className="library-toolbar">
        <label className="search-box">
          <Search size={17} />
          <input
            placeholder="Search your resources..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
        >
          <option>All sources</option>
          {kinds.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </div>
      <div className="library-list">
        {librarySources.map((s) => (
          <div className="library-item" key={s.id}>
            <Resource
              source={s}
              onRetry={() => retry.mutate(s.id)}
              onViewGraph={() => onViewGraph(s.id)}
              job={jobs.filter((j) => j.source_id === s.id).at(-1)}
            />
            <div className="resource-actions">
              <button
                disabled={active(s.status) || retry.isPending}
                onClick={() => retry.mutate(s.id)}
                title="Refresh or retry"
              >
                <RotateCcw size={16} />
              </button>
              <button
                disabled={active(s.status) || remove.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete “${s.title}” and its source evidence?`,
                    )
                  )
                    remove.mutate(s.id);
                }}
                title="Delete resource"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
        {!librarySources.length && (
          <div className="library-empty">
            <Library size={36} />
            <h2>Your collection starts here.</h2>
            <p>Add a resource to get started.</p>
            <button className="primary" onClick={() => onAdd()}>
              <Plus size={16} />
              Add Knowledge
            </button>
          </div>
        )}
      </div>
      {(remove.error || retry.error) && (
        <p role="alert" className="error">
          {remove.error?.message || retry.error?.message}
        </p>
      )}
    </>
  );
}
