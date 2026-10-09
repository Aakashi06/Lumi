"""Opt-in full API workflow against the exact configured local model servers."""

import os
import time

import pymupdf
import pytest
from fastapi.testclient import TestClient
from lumi.main import app


@pytest.mark.skipif(
    os.getenv("LUMI_REAL_MODELS") != "1",
    reason="Set LUMI_REAL_MODELS=1 with local Qwen endpoints running",
)
def test_real_local_workflow():
    text = "Vector search uses embeddings to find similar documents. Embeddings represent text as numeric vectors."
    document = pymupdf.open()
    document.new_page().insert_textbox((50, 50, 500, 700), text)
    started = time.perf_counter()
    with TestClient(app) as client:
        result = client.post(
            "/api/sources/pdf",
            files={"file": ("VERIFICATION SAMPLE.pdf", document.tobytes(), "application/pdf")},
        )
        assert result.status_code == 202
        job_id = result.json()["job_id"]
        deadline = time.perf_counter() + 180
        while time.perf_counter() < deadline:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["stage"] in {"completed", "failed"}:
                break
            time.sleep(0.5)
        assert job["stage"] == "completed", job
        graph = client.get("/api/graph").json()
        assert len(graph["nodes"]) >= 2 and graph["edges"]
        response = client.post(
            "/api/chat", json={"query": "How does vector search use embeddings?"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["citations"] and "[1]" in response.json()["answer"]
        print(f"Real PDF → graph → cited answer: {time.perf_counter() - started:.2f}s")
