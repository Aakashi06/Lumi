"""Local inference adapter; business logic never depends on a runtime SDK."""

import json
import math
from typing import Protocol

import httpx

from .config import settings


class ModelAdapter(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def generate(
        self, system: str, prompt: str, schema: dict | None = None, max_tokens: int | None = None
    ) -> dict: ...


class LocalModels:
    async def verify_model(self, client: httpx.AsyncClient, endpoint: str, identifier: str):
        response = await client.get(f"{endpoint}/models")
        response.raise_for_status()
        available = {item["id"] for item in response.json()["data"]}
        if identifier not in available:
            raise ValueError(
                f"Requested model {identifier} is unavailable at {endpoint}. No substitute will be used."
            )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=settings.timeout, trust_env=False) as client:
            await self.verify_model(client, settings.embedding_url, settings.embedding_id)
            response = await client.post(
                f"{settings.embedding_url}/embeddings",
                json={
                    "model": settings.embedding_id,
                    "input": texts,
                },
            )
            response.raise_for_status()
            vectors = sorted(response.json()["data"], key=lambda item: item["index"])
            if len(vectors) != len(texts):
                raise ValueError("Embedding endpoint returned an incorrect number of vectors")
            embeddings = [item["embedding"] for item in vectors]
            if any(
                not vector
                or any(
                    not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in vector
                )
                for vector in embeddings
            ):
                raise ValueError("Embedding endpoint returned invalid numeric vectors")
            if len({len(vector) for vector in embeddings}) > 1:
                raise ValueError("Embedding dimensions must be consistent")
            return embeddings

    async def generate(
        self, system: str, prompt: str, schema: dict | None = None, max_tokens: int | None = None
    ) -> dict:
        output_limit = min(max_tokens or settings.max_tokens, settings.max_tokens)
        # Conservative character budget; the runtime still enforces its actual token limit.
        if len(system) + len(prompt) > (settings.context_window - output_limit - 300) * 2:
            raise ValueError(
                "Prompt exceeds the configured context budget. Reduce retrieval or increase local context."
            )
        async with httpx.AsyncClient(timeout=settings.timeout, trust_env=False) as client:
            await self.verify_model(client, settings.model_url, settings.model_id)
            response = await client.post(
                f"{settings.model_url}/chat/completions",
                json={
                    "model": settings.model_id,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": settings.temperature,
                    "max_tokens": output_limit,
                    "response_format": {
                        "type": "json_object",
                        **({"schema": schema} if schema else {}),
                    },
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(content)
