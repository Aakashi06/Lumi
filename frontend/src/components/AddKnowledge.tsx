import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { Sparkles, X, Upload, Plus, LoaderCircle } from "lucide-react";
import { api, type Source } from "../api";

export default function AddKnowledge({
  close,
  onSubmitted,
}: {
  close: () => void;
  onSubmitted: (source: Source) => void;
}) {
  const client = useQueryClient();
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const chooseFile = (chosen: File | null) => {
    const error =
      chosen && !/\.(pdf|docx|txt|md)$/i.test(chosen.name)
        ? "Choose PDF, Word (.docx), or text (.txt/.md)."
        : chosen && chosen.size > 12 * 1024 * 1024
          ? "Choose a document under 12 MB."
          : null;
    setFileError(error);
    setFile(error ? null : chosen);
  };
  const [file, setFile] = useState<File | null>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      if (!file)
        throw new Error("Choose a PDF, Word document, or text file first.");
      const body = new FormData();
      body.append("file", file);
      return api<{ source: Source }>("/sources/upload", {
        method: "POST",
        body,
      });
    },
    onSuccess: (result) => {
      onSubmitted(result.source);
      client.invalidateQueries({ queryKey: ["sources"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      close();
    },
  });
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [close]);
  return (
    <div className="overlay" onClick={close}>
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          className="icon-button close"
          onClick={close}
          aria-label="Close"
        >
          <X size={20} />
        </button>
        <div className="modal-symbol">
          <Sparkles size={25} />
        </div>
        <h2 id="add-title">Build from a document.</h2>
        <p>PDF, Word, or plain text.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <label
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              chooseFile(event.dataTransfer.files[0] || null);
            }}
          >
            <Upload size={26} />
            <strong>{file?.name || "Drop your document here"}</strong>
            <span>
              {file
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB · click to choose another`
                : "or click to browse · up to 12 MB"}
            </span>
            <input
              aria-label="Document file"
              type="file"
              accept=".pdf,.docx,.txt,.md"
              onChange={(event) => chooseFile(event.target.files?.[0] || null)}
            />
          </label>
          <div className="local-note">
            <span className="status-dot" />
            Processed on your Mac · no cloud upload
          </div>
          {fileError && (
            <p role="alert" className="error">
              {fileError}
            </p>
          )}
          {mutation.error && (
            <p role="alert" className="error">
              {mutation.error.message}
            </p>
          )}
          <button
            className="primary full"
            disabled={mutation.isPending || !file}
          >
            {mutation.isPending ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Plus size={17} />
            )}{" "}
            {mutation.isPending ? "Uploading…" : "Make your knowledge graph"}
          </button>
        </form>
      </motion.section>
    </div>
  );
}
