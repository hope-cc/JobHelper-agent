# 招聘信息向量库与 RAG 检索 Plan

## 架构概览

新增 `src/rag/` 包（embedding + 向量库），改造 `src/sub_agent/dispatcher.py` 自动入库，新增 `searchJobs` 工具并更新提示词。

```
子 agent 完成 → _result_queue
   │  dispatcher 后台消费协程（懒启动，首次 dispatch 时）
   ▼
[解析容错] 剥围栏→列表/单对象→逐条职位
   │  去重集合 set[(公司,职位)] 命中则跳过
   ▼
JobVectorStore.add_job() ── chromadb(PersistentClient, data/vector)
                          └─ 稠密向量由 OllamaEmbeddingFunction → ollama bge-m3

主 agent 对话 ── searchJobs(query, top_k) → JobVectorStore.search()
   ├─ 稠密路：chroma query(query_texts) → cosine 排序
   ├─ 稀疏路：jieba 分词 + BM25Okapi → 打分排序
   └─ RRF(k=60)：两路排名融合 → top_k 职位 JSON
```

## 核心数据结构

**职位记录**（来自 worker.py 定义的字段）

| 字段 | 说明 |
|------|------|
| 公司 / 职位 | 去重键来源；缺失则该条跳过不入库 |
| 工作职责 / 任职要求 / 工作地点 / 投递方式 | 检索与展示内容 |

**chromadb 单条记录**

| 部分 | 内容 |
|------|------|
| id | `sha1(公司 \x1f 职位)` 的 hex —— 确定性 id，天然幂等 |
| document | 六字段拼接全文（`公司：…\n职位：…`），供嵌入与 BM25 |
| metadata | 英文键结构化：`company, position, duties, requirements, location, apply_method` |

**去重集合**：`set[tuple[str, str]]`，以「公司+职位」为键，启动时从向量库 `all_records()` 重建。

**BM25 索引**：`BM25Okapi([jieba.lcut(doc) for doc in 全部职位文本])`，带 dirty 标记按需重建。

**RRF**：`score(doc) = Σ 1/(60 + rank)`，rank 为各检索路的名次（1 开始）。

## 模块设计

### src/rag/embedding.py — `OllamaEmbeddingFunction`

**职责：** 把 ollama bge-m3 封装成 chromadb `EmbeddingFunction[Documents]`。

**对外接口：**
- `OllamaEmbeddingFunction(base_url: str, model: str)`
- `__call__(input: list[str]) -> list[list[float]]` —— POST `/api/embed`，`{"model", "input"}`，取 `embeddings`

**依赖：** requests（已装）

### src/rag/store.py — `JobVectorStore`（单例 `job_vector_store`）

**职责：** chromadb 持久化 + 混合检索（稠密 + BM25 + RRF）。

**对外接口：**
- `configure(*, ollama_base_url, embedding_model, vector_dir, retrieval_top_k)` —— 启动时注入；未调用则用默认值（`retrieval_top_k` 为 searchJobs 默认返回条数，区别于 RRF 的 k=60）
- `add_job(job: dict) -> bool` —— 写单条职位；`True`=新增写入，`False`=异常
- `search(query: str, top_k: int) -> list[dict]` —— 混合检索，返回职位字段 dict 列表
- `all_records() -> list[dict]` —— 全量记录（供去重集合重建 / BM25 索引）

**内部：**
- chroma 集合懒初始化（`PersistentClient(vector_dir)` + 集合 `jobs`，绑定 OllamaEmbeddingFunction）
- `_records` 内存缓存 + BM25 索引（dirty 时重建）
- 稠密查询失败（ollama 不可用）时降级 BM25-only；两者都失败返回空并标记

### src/sub_agent/dispatcher.py（改造）

**职责：** 自动消费 `_result_queue` 并入库，维护去重集合。

**新增：**
- `_known_jobs: set[tuple[str, str]]`
- `_ensure_consumer()`：幂等懒启动后台协程，循环 `await _result_queue.get()` → `_ingest_result()`
- `_ingest_result(result)`：非成功跳过 → 容错解析（剥 ``` 围栏、单 dict 转 list、非 JSON 记录并跳过）→ 逐条：缺公司/职位跳过、在 `_known_jobs` 中跳过、否则 `add_job` 成功后加入集合
- `_load_known_jobs()`：从 `job_vector_store.all_records()` 重建

**修改：** `dispatch()` 追加任务前 `_ensure_consumer()` + `_load_known_jobs()`；移除 `drain_results()` 的「主动拉取」语义（返回空；`wait_all()` 仅等完成不返回结果）

**依赖：** src/rag/store.py

### src/tools/builtin/search_jobs.py — `searchJobs` 工具

**职责：** RAG 查询工具，主 agent 传入问题检索职位。

**参数：** `query`（必填，用户问题/关键词）、`top_k`（默认 5，上限 20）

**逻辑：** `job_vector_store.search(query, top_k)` → 有结果返回 JSON 数组；空库/检索异常返回明确中文提示，不抛异常

**依赖：** src/rag/store.py

### src/prompt/prompt.py（改造）

ToolUse 段加一条：用户询问已收集的招聘信息（某公司/某类职位的岗位、要求、投递方式）时调用 searchJobs 检索。

### src/api/main.py（改造）

`load_app_settings` 后读取 `settings.rag`，调用 `job_vector_store.configure(...)`。

### 配置文件

`config.example.yaml` 增加 `settings.rag` 示例；`requirements.txt` 增加 `jieba`、`rank_bm25`。

## 模块交互

1. **入库链路**：子 agent 完成任务 → `_result_queue.put(TaskResult)` → dispatcher 后台协程 `get()` → `_ingest_result()`（去重检查）→ `JobVectorStore.add_job()` → chroma 调 OllamaEmbeddingFunction 生成向量落库，同时追加内存缓存并置 BM25 dirty。
2. **检索链路**：主 agent 调 `searchJobs` → `search()` → 稠密路 chroma query（`n_results=max(top_k*2,10)` 候选池）→ 稀疏路 BM25 打分排序 → 两路 union 后 RRF 融合 → top_k 组装职位 dict 返回。

## 文件组织

```
src/rag/
├── __init__.py
├── embedding.py          — OllamaEmbeddingFunction
└── store.py              — JobVectorStore + 混合检索
src/sub_agent/
└── dispatcher.py         — 改造：自动消费入库 + 去重集合
src/tools/builtin/
└── search_jobs.py        — 新增 searchJobs 工具
src/prompt/prompt.py      — 改造：加 searchJobs 使用指引
src/api/main.py           — 改造：注入 settings.rag 到 job_vector_store.configure()
config.example.yaml       — 改造：settings.rag 示例
requirements.txt          — 新增 jieba、rank_bm25
docs/招聘信息向量库与RAG检索/  — 四份文档
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 稠密向量 | ollama `/api/embed` + bge-m3，自定义 EF | 用户指定；本地推理无云端依赖 |
| 关键词路 | rank_bm25 `BM25Okapi` + jieba 分词 | 中文职位文本需词级分词，BM25 质量决定关键词匹配（方案1已确认） |
| 融合 | 手写 RRF，k=60 | 用户指定；RRF 只需两路名次，无需分数归一化 |
| 混合检索位置 | 不依赖 chroma 原生混合（本地不支持，已核实） | chroma 1.5.9 本地 query 仅 KNN，`search()` 混合 API 仅 hosted |
| 去重 | dispatcher 持 `set[(公司,职位)]`，启动从向量库重建 | 单一数据源，重启不丢；deterministic id 兜底幂等 |
| 后台入库 | dispatcher 内懒启动 asyncio 消费协程 | 与「自动检测」意图一致；避免 import 时无事件循环 |
| 解析容错 | 剥围栏→list/dict→逐条，失败跳过记录 | 子 agent LLM 输出不稳定 |
| 检索降级 | 稠密失败时降级 BM25-only；都失败返回提示 | 满足 F6，不中断对话 |
| 配置 | `settings.rag` 默认值兜底 | 不配置也能跑 |
| BM25 索引更新 | 内存缓存 + dirty 标志按需重建 | 规模小（百级），重建成本可接受 |

## 环境前置

- `D:/coding/Anaconda/envs/agent/python.exe -m pip install jieba rank_bm25`
- `ollama pull bge-m3`
