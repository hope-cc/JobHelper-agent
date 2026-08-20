# 招聘信息向量库与 RAG 检索 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/rag/__init__.py` | 空包标记 |
| 新建 | `src/rag/embedding.py` | OllamaEmbeddingFunction |
| 新建 | `src/rag/store.py` | JobVectorStore + 混合检索 |
| 修改 | `src/sub_agent/dispatcher.py` | 自动入库 + 去重集合 |
| 新建 | `src/tools/builtin/search_jobs.py` | searchJobs 工具 |
| 修改 | `src/prompt/prompt.py` | searchJobs 使用指引 |
| 修改 | `src/api/main.py` | 注入 rag 配置 |
| 修改 | `config.example.yaml` | settings.rag 示例 |
| 修改 | `requirements.txt` | 新增 jieba、rank_bm25 |

**环境前置（T1 会执行，请先确认已装）**
- `D:/coding/Anaconda/envs/agent/python.exe -m pip install jieba rank_bm25`
- `ollama pull bge-m3`

## T1: 配置与依赖基座

**文件：** `requirements.txt`、`config.example.yaml`
**依赖：** 无
**步骤：**
1. `requirements.txt` 追加 `jieba`、`rank_bm25`
2. `config.example.yaml` 顶层加 settings 段（含 rag 示例）：
```yaml
settings:
  max_concurrency: 3
  rag:
    ollama_base_url: "http://localhost:11434"
    embedding_model: "bge-m3"
    retrieval_top_k: 5
    vector_dir: "data/vector"
```
**验证：** `D:/coding/Anaconda/envs/agent/python.exe -c "import jieba, rank_bm25"` 无报错；`load_app_settings` 能读出 rag 段

## T2: 嵌入封装

**文件：** `src/rag/__init__.py`、`src/rag/embedding.py`
**依赖：** 无
**步骤：**
1. 建 `src/rag/__init__.py`（空文件）
2. `embedding.py` 定义 `OllamaEmbeddingFunction(EmbeddingFunction[Documents])`：`__init__(base_url, model)`；`__call__(input)` 调 POST `{base_url}/api/embed` `{"model", "input"}`，返回 `resp.json()["embeddings"]`，超时 60s
**验证：** `python -c` 实例化并对 `["测试文本"]` 调用，返回 1024 维浮点向量（需 bge-m3 已拉取）

## T3: 向量库与混合检索

**文件：** `src/rag/store.py`
**依赖：** T2
**步骤：**
1. `JobVectorStore`：`configure()` 存配置；chroma 集合懒初始化（`PersistentClient(vector_dir)` + `get_or_create_collection("jobs", embedding_function=OllamaEmbeddingFunction(...))`）
2. `add_job(job)`：id=`sha1(公司+\x1f+职位)`；document=六字段拼接全文；metadata=英文键 `company/position/duties/requirements/location/apply_method`；`collection.add(...)` 后更新 `_records` 缓存并置 BM25 dirty
3. `all_records()`：从缓存返回（首次从 `collection.get(include=["documents","metadatas"])` 加载）
4. `search(query, top_k)`：若 BM25 dirty 用 `BM25Okapi([jieba.lcut(doc)...])` 重建；稠密路 `collection.query(query_texts=[query], n_results=max(top_k*2,10), include=["metadatas","documents","distances"])`；稀疏路 `bm25.get_scores(jieba.lcut(query))`；两路 union 后 RRF(k=60) 融合取 top_k，组装职位 dict 列表
5. 稠密路异常时降级 BM25-only；两者皆败返回空
**验证：** 临时脚本 `configure → add_job(两条) → search("后端开发")`，返回含目标职位且顺序合理

## T4: 调度器自动入库

**文件：** `src/sub_agent/dispatcher.py`
**依赖：** T3
**步骤：**
1. 新增 `_known_jobs: set[tuple[str,str]]`
2. 新增 `_ensure_consumer()`（幂等）与后台协程：循环 `await self._result_queue.get()` → `_ingest_result()`
3. 新增 `_ingest_result(result)`：`not success` 跳过 → `json.loads` 容错（剥围栏、dict 转 list、失败记录并跳过）→ 逐条：缺公司/职位跳过、在 `_known_jobs` 中跳过、`job_vector_store.add_job()` 成功后加入集合
4. 新增 `_load_known_jobs()`：从 `job_vector_store.all_records()` 重建 `(company, position)` 集合
5. `dispatch()` 前置调用 `_ensure_consumer()` + `_load_known_jobs()`
6. `drain_results()` 改为返回空列表；`wait_all()` 仅等完成、返回空列表
**验证：** 临时脚本：`dispatch` 后向 `_result_queue` 手动 `put` 一个含 2 条职位的 TaskResult，sleep 后 `job_vector_store.all_records()` 增加 2；重复 put 同「公司+职位」，记录数不变

## T5: searchJobs 工具

**文件：** `src/tools/builtin/search_jobs.py`
**依赖：** T3
**步骤：**
1. Pydantic 参数模型：`query`(必填)、`top_k`(默认 5)
2. `@tool(name="searchJobs", description=...)`：`job_vector_store.search(query, top_k)` → 结果转 JSON 字符串；空库/异常返回中文提示
3. description 写清适用场景（查询已抓取的招聘信息）
**验证：** `registry.execute("searchJobs", {"query": "后端开发", "top_k": 3})` 返回职位 JSON 或可读提示

## T6: 提示词指引

**文件：** `src/prompt/prompt.py`
**依赖：** 无
**步骤：** ToolUse 段追加一条：用户询问已收集招聘信息（岗位要求/投递方式/某公司某类职位）时，调用 searchJobs 检索
**验证：** `build_system_prompt()` 输出包含该规则

## T7: 启动注入配置

**文件：** `src/api/main.py`
**依赖：** T1、T3
**步骤：** `load_app_settings` 后读取 `settings.rag`（缺省用默认值），调用 `job_vector_store.configure(...)`
**验证：** 启动后端无异常，日志可见 store 配置

## T8: 端到端手测

**依赖：** T1–T7
**步骤：**
1. 启动后端 + 前端，让主 agent 对招聘网站执行 dispatchTasks
2. 子 agent 返回后，观察 `data/vector` 目录生成 chroma 数据文件
3. 对话中让主 agent「查询 XX 岗位」，观察 searchJobs 调用并返回职位 JSON
**验证：** `data/vector` 有持久化文件；重启后端后 `searchJobs` 仍能查到历史职位（数据不丢）

## 执行顺序

```
T1 → T2 → T3 → T4
            ↘
T5（与 T4 并行）→ T6 → T7 → T8
```
