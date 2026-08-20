"""招聘职位向量库与混合检索。

JobVectorStore 封装 chromadb 持久化集合（数据目录 data/vector）：
    - add_job:   写入单条职位（稠密向量由 OllamaEmbeddingFunction 生成）
    - search:    稠密检索（chroma KNN）+ 稀疏检索（jieba 分词 + BM25）
                 两路结果经 RRF 融合后返回 top_k。
    - all_records: 全量记录，供调度器去重集合重建 / BM25 索引。

chroma 本地不支持原生混合检索（其 search()/稀疏融合为 hosted 专属），
故稠密与稀疏两路在此手动实现并做 RRF 融合。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from chromadb import PersistentClient

from src.rag.embedding import OllamaEmbeddingFunction

# RRF 融合常数（经典取值 60）
_RRF_K = 60

# 六个字段：中文键（worker 输出格式）→ 英文元数据键
_JOB_FIELDS = [
    ("公司", "company"),
    ("职位", "position"),
    ("工作职责", "duties"),
    ("任职要求", "requirements"),
    ("工作地点", "location"),
    ("投递方式", "apply_method"),
]

# 向量库默认持久化目录（相对项目根）
_DEFAULT_VECTOR_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "data" / "vector"
)


class JobVectorStore:
    """职位向量库（全局单例 job_vector_store）。

    集合懒初始化：首次 add_job / search 时才打开 chromadb。
    configure() 可在启动时注入配置；未调用则用默认值。
    """

    def __init__(self) -> None:
        self._ollama_base_url = "http://localhost:11434"
        self._embedding_model = "bge-m3"
        self._vector_dir = _DEFAULT_VECTOR_DIR
        self._retrieval_top_k = 5

        self._client = None
        self._collection = None
        # 内存缓存：全量职位记录 [{"id", "document", "metadata"}]
        self._records: list[dict] | None = None
        # BM25 索引（jieba 分词后构建），新增记录后置 dirty 按需重建
        self._bm25 = None
        self._bm25_dirty = True

    def configure(
        self,
        *,
        ollama_base_url: str | None = None,
        embedding_model: str | None = None,
        vector_dir: str | None = None,
        retrieval_top_k: int | None = None,
    ) -> None:
        """注入配置；None 表示保留当前值（含默认值）。

        retrieval_top_k 为 searchJobs 默认返回条数，区别于 RRF 常数 k=60。
        """
        if ollama_base_url is not None:
            self._ollama_base_url = ollama_base_url
        if embedding_model is not None:
            self._embedding_model = embedding_model
        if vector_dir is not None:
            # 相对路径基于项目根解析为绝对路径，避免启动目录不同导致错位
            p = Path(vector_dir)
            if not p.is_absolute():
                p = Path(__file__).resolve().parent.parent.parent / p
            self._vector_dir = str(p)
        if retrieval_top_k is not None:
            self._retrieval_top_k = retrieval_top_k

    # ---- 内部：懒初始化 ----

    def _ensure_init(self) -> None:
        if self._collection is not None:
            return
        self._client = PersistentClient(path=self._vector_dir)
        ef = OllamaEmbeddingFunction(self._ollama_base_url, self._embedding_model)
        self._collection = self._client.get_or_create_collection(
            name="jobs",
            embedding_function=ef,
        )

    def _load_records(self) -> None:
        """从集合一次性加载全量记录到内存缓存。"""
        if self._records is not None:
            return
        got = self._collection.get(include=["documents", "metadatas"])
        ids = got["ids"]
        docs = got["documents"] or []
        metas = got["metadatas"] or []
        self._records = [
            {"id": i, "document": d, "metadata": m}
            for i, d, m in zip(ids, docs, metas)
        ]

    # ---- 写入 ----

    def add_job(self, job: dict) -> bool:
        """写入单条职位记录，返回是否成功。

        id 由「公司+职位」哈希生成（确定性，天然幂等——同 id 重复 add
        会覆盖旧记录，不会产生重复条目）。去重集合由调用方
        （dispatcher 的 _known_jobs）负责，此处不做重复判断。
        """
        company = str(job.get("公司", "") or "")
        position = str(job.get("职位", "") or "")
        if not company or not position:
            return False

        self._ensure_init()
        self._load_records()

        doc_id = hashlib.sha1(
            f"{company}\x1f{position}".encode("utf-8")
        ).hexdigest()

        document = "\n".join(
            f"{label}：{job.get(label, '')}" for label, _ in _JOB_FIELDS
        )
        metadata = {key: job.get(label, "") for label, key in _JOB_FIELDS}

        try:
            self._collection.add(
                ids=[doc_id],
                documents=[document],
                metadatas=[metadata],
            )
        except Exception:
            return False

        # 同步内存缓存：同 id 重复 add 时 chroma 为覆盖语义，
        # 缓存也应替换而非追加，避免 count() 虚增。
        entry = {"id": doc_id, "document": document, "metadata": metadata}
        existing_idx = next(
            (i for i, rec in enumerate(self._records) if rec["id"] == doc_id),
            None,
        )
        if existing_idx is not None:
            self._records[existing_idx] = entry
        else:
            self._records.append(entry)

        self._bm25_dirty = True
        return True

    def all_records(self) -> list[dict]:
        """返回全量记录列表（浅拷贝）。"""
        self._ensure_init()
        self._load_records()
        return list(self._records)

    def count(self) -> int:
        return len(self.all_records())

    # ---- 检索 ----

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """混合检索：稠密(KNN) + 稀疏(BM25) → RRF 融合 → top_k 职位 dict。

        稠密路异常（如 ollama 不可用）时自动降级为 BM25-only；
        两者皆无可返回时返回空列表。
        """
        top_k = top_k or self._retrieval_top_k
        if not query.strip():
            return []

        records = self.all_records()
        if not records:
            return []

        self._ensure_bm25()

        # 1. 稠密路：chroma KNN（query_texts 由 embedding function 自动向量化）
        dense_ids: list[str] = []
        try:
            res = self._collection.query(
                query_texts=[query],
                n_results=max(top_k * 2, 10),
                include=["distances"],
            )
            dense_ids = res["ids"][0]
        except Exception:
            dense_ids = []  # 降级为 BM25-only

        # 2. 稀疏路：BM25 打分，按分降序取 rank（分>0 才计入）
        query_tokens = self._tokenize(query)
        scores = self._bm25.get_scores(query_tokens)
        order = sorted(range(len(records)), key=lambda i: -scores[i])
        sparse_rank = {
            records[i]["id"]: rank + 1
            for rank, i in enumerate(order)
            if scores[i] > 0
        }

        # 3. RRF 融合：两路名次的倒数求和
        rrf: dict[str, float] = {}
        for rank, doc_id in enumerate(dense_ids, start=1):
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank)
        for doc_id, rank in sparse_rank.items():
            rrf[doc_id] = rrf.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank)

        if not rrf:
            return []

        ranked_ids = sorted(rrf, key=lambda i: -rrf[i])[:top_k]
        by_id = {r["id"]: r for r in records}
        return [
            self._job_dict(by_id[doc_id]["metadata"])
            for doc_id in ranked_ids
            if doc_id in by_id
        ]

    # ---- 内部辅助 ----

    def _job_dict(self, meta: dict) -> dict:
        """metadata(英文键) → 职位 dict(中文键，与 worker 输出一致)。"""
        return {
            label: meta.get(key, "")
            for label, key in _JOB_FIELDS
        }

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import jieba

        return jieba.lcut(text)

    def _ensure_bm25(self) -> None:
        if not self._bm25_dirty and self._bm25 is not None:
            return
        from rank_bm25 import BM25Okapi

        tokenized = [self._tokenize(r["document"]) for r in self._records]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_dirty = False


# ---- 全局单例 ----

job_vector_store = JobVectorStore()
