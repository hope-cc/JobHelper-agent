"""Ollama 稠密嵌入封装。

把本地 ollama 的 bge-m3 封装为 chromadb 可用的 EmbeddingFunction，
使 chroma 在 add / query 时自动调用 ollama 生成向量。
"""

from __future__ import annotations

import requests

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """通过 ollama HTTP API 生成稠密向量（默认 bge-m3）。

    bge-m3 输出 1024 维向量。调用 POST {base_url}/api/embed，
    请求体 {"model", "input"}，从响应的 embeddings 字段取向量列表。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        resp = requests.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": list(input)},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]
