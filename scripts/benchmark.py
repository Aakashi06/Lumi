#!/usr/bin/env python3
"""Manual benchmarks in disposable databases. Never reads or changes Lumi's DB."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import tracemalloc
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
GOLD_TEXT = "SQLite uses Python. NetworkX requires Python. Retrieval uses embeddings."
GOLD_ENTITIES = {"sqlite", "python", "networkx", "retrieval", "embeddings"}


class NoModels:
    async def generate(self, *args, **kwargs):
        raise AssertionError("Ingestion must not invoke an LLM")

    async def embed(self, *args, **kwargs):
        raise AssertionError("Default ingestion must not invoke embedding inference")


def quality():
    from lumi.local_extraction import extract
    from lumi.telemetry import Timings

    result = extract(GOLD_TEXT, Timings())
    predicted = {hit["key"] for hit in result["hits"]}
    matched = len(predicted & GOLD_ENTITIES)
    semantic = {(e["source"], e["relation"], e["target"]) for e in result["edges"] if e["verified"]}
    expected = {
        ("sqlite", "USES", "python"),
        ("networkx", "REQUIRES", "python"),
        ("retrieval", "USES", "embeddings"),
    }
    return dict(
        precision=matched / max(len(predicted), 1),
        recall=matched / len(GOLD_ENTITIES),
        relationship_recall=len(semantic & expected) / len(expected),
        predicted_entities=sorted(predicted),
        note="Synthetic sanity check, not a representative real-document accuracy evaluation",
    )


def worker(path, output):
    # Set isolation before importing settings or the database module.
    with tempfile.TemporaryDirectory(prefix="lumi-benchmark-") as folder:
        os.environ["LUMI_DATABASE_URL"] = f"sqlite:///{folder}/benchmark.db"
        os.environ["LUMI_ENABLE_EMBEDDINGS"] = "false"
        sys.path.insert(0, str(ROOT / "backend"))
        from lumi.db import Job, Session, Source, initialize_database, serialize
        from lumi.graph_store import read_graph
        from lumi.indexing import initialize_search
        from lumi.pipeline import Pipeline, content_hash
        from lumi.telemetry import TimedJSONResponse

        initialize_database()
        initialize_search()
        runner = Pipeline(NoModels())
        source_id = str(uuid4())
        tracemalloc.start()

        async def run():
            results = []
            # Cold NLP load included in cold; second upload exercises global caches;
            # retry of that upload exercises the unchanged-document fast path.
            for mode in ("cold", "cached_upload", "unchanged"):
                nonlocal source_id
                with Session.begin() as session:
                    if mode != "unchanged":
                        source_id = str(uuid4())
                        source = Source(
                            id=source_id,
                            kind="txt" if path.suffix == ".md" else path.suffix[1:],
                            title=path.name,
                            file_path=str(path),
                        )
                        session.add(source)
                        session.flush()
                    job_id = str(uuid4())
                    session.add(Job(id=job_id, source_id=source_id))
                start = time.perf_counter()
                await runner.run(job_id)
                elapsed = time.perf_counter() - start
                with Session() as session:
                    job = session.get(Job, job_id)
                    result = serialize(job)
                result["mode"] = mode
                result["wall_seconds"] = round(elapsed, 4)
                results.append(result)
            return results

        results = asyncio.run(run())
        graph_started = time.perf_counter()
        graph = read_graph()
        graph_ms = (time.perf_counter() - graph_started) * 1000
        response = TimedJSONResponse(graph)
        _, python_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        # macOS reports bytes, Linux KiB; native RSS includes spaCy / NumPy memory.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss / (1024**2 if sys.platform == "darwin" else 1024)
        report = dict(
            document=path.name,
            content_hash=content_hash(path),
            results=results,
            peak_rss_mb=round(rss_mb, 2),
            python_peak_mb=round(python_peak / 1024**2, 2),
            graph_read_ms=round(graph_ms, 3),
            json_serialization_ms=response.serialization_ms,
            visible_nodes=len(graph["nodes"]),
            total_nodes=graph["total_nodes"],
            extraction_quality=quality(),
            memory_scope="Peak across cold, cached upload and unchanged retry in one isolated process",
        )
        Path(output).write_text(json.dumps(report, indent=2))


def fixtures(folder):
    import pymupdf
    from docx import Document

    paths = []
    for size, pages in (("small", 3), ("medium", 30)):
        paragraphs = [
            GOLD_TEXT
            + "\n"
            + "Knowledge graphs organize concepts. Vector search finds documents. " * 8
            for _ in range(pages)
        ]
        txt = folder / f"{size}.txt"
        txt.write_text("\n\n".join(paragraphs))
        word = Document()
        pdf = pymupdf.open()
        for text in paragraphs:
            word.add_paragraph(text)
            page = pdf.new_page()
            page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), text, fontsize=11)
        docx, pdf_path = folder / f"{size}.docx", folder / f"{size}.pdf"
        word.save(docx)
        pdf.save(pdf_path)
        pdf.close()
        paths.extend((txt, docx, pdf_path))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document",
        action="append",
        type=Path,
        help="Optional real PDF/DOCX/TXT; otherwise generate 3/30-page fixtures",
    )
    parser.add_argument("--output", default="benchmarks/after.json")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker.resolve(), args.output)
        return
    with tempfile.TemporaryDirectory(prefix="lumi-fixtures-") as folder:
        paths = args.document or fixtures(Path(folder))
        reports = []
        for index, path in enumerate(paths):
            output = Path(folder) / f"result-{index}.json"
            subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "--worker",
                    str(path.resolve()),
                    "--output",
                    str(output),
                ],
                check=True,
            )
            reports.append(json.loads(output.read_text()))
        baseline_path = ROOT / "benchmarks/baseline.json"
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
        comparisons = []
        for report in reports:
            before = next(
                (
                    item
                    for item in baseline.get("records", [])
                    if item.get("content_hash") == report["content_hash"]
                ),
                None,
            )
            cold = report["results"][0]
            comparisons.append(
                dict(
                    document=report["document"],
                    before=before,
                    after_seconds=cold["wall_seconds"],
                    speedup=(
                        before["observed_elapsed_seconds"] / cold["wall_seconds"]
                        if before
                        and before["stage"] == "completed"
                        and cold["stage"] == "completed"
                        else None
                    ),
                    note="Speedup requires a completed baseline for the identical file. In-progress observations are not comparable benchmarks.",
                )
            )
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                dict(pipeline="pipeline-v4.1-local-nlp", reports=reports, comparisons=comparisons),
                indent=2,
            )
        )
        print(f"Saved manual measurements to {target.resolve()}")
        if any(job["stage"] != "completed" for report in reports for job in report["results"]):
            raise SystemExit("One or more document jobs failed; inspect the report.")


if __name__ == "__main__":
    main()
