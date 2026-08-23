# 投递进度管理 Plan

## 架构概览

沿用项目既有的「storage + routes」模式：

- **后端**：`job_storage.py` 负责 `data/jobs.json` 文件的读写（单一 JSON 数组）；`job_routes.py` 提供 REST 接口（列表、新增、更新），并在 `routes.py` 挂载。统计、搜索、排序、CSV 导出全部在前端完成——数据量小，一次全量拉取，后端保持「无业务逻辑的纯持久层」。
- **前端**：`JobProgressPage.tsx` 为页面主组件，持有记录数据，拆出四个子组件：`MetricCards`（统计卡片）、`JobToolbar`（搜索/筛选/排序/导出）、`JobTable`（表格）、`JobFormModal`（新增/编辑弹窗）。页面级状态用组件内 state 管理（页面自包含，无需 Context）。
- **数据流**：进入页面 → `GET /api/jobs` 拉全量 → 前端按「搜索词 + 进度筛选 + 排序」派生显示列表 → 统计卡片对同一数据源实时计算 → 新增/编辑提交后刷新列表。

## 核心数据结构

### 后端存储格式 `data/jobs.json`

```json
[
  {
    "id": "uuid4 字符串",
    "company": "字节跳动",
    "position": "后端开发工程师",
    "applied_at": "2026-08-23",
    "status": "评估中",
    "next_step": "等待一面通知",
    "remark": ""
  }
]
```

### 前端类型（`types.ts`）

```ts
export type JobStatus = "简历已投递" | "评估中" | "Offer" | "已拒绝";

export interface JobRecord {
  id: string;
  company: string;       // 必填
  position: string;      // 必填
  applied_at: string;    // YYYY-MM-DD
  status: JobStatus;
  next_step: string;
  remark: string;        // 可空
}
```

### 状态徽标映射（`JobTable.tsx` 内常量）

```ts
const JOB_STATUS_STYLE: Record<JobStatus, string> = {
  "评估中":     "bg-amber-50 text-amber-700 border-amber-200",
  "简历已投递": "bg-sky-50 text-sky-700 border-sky-200",
  "Offer":     "bg-emerald-50 text-emerald-700 border-emerald-200",
  "已拒绝":     "bg-rose-50 text-rose-700 border-rose-200",
};
```

### 后端 API 契约（`job_routes.py`）

| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| GET | `/api/jobs` | — | `{"jobs": [...]}` 全量 |
| POST | `/api/jobs` | `{company, position, applied_at, status, next_step, remark}` | 200 + 新建记录（含 id） |
| PUT | `/api/jobs/{job_id}` | 同上 | 200 + 更新后的记录 |

- `status` 必须在四选一集合内，否则 422
- `applied_at` 必须是 `YYYY-MM-DD` 格式，否则 422
- `company` / `position` 非空，否则 422
- PUT 时 id 不存在返回 404

## 模块设计

### 后端 `job_storage.py`

**职责：** `data/jobs.json` 的读写（读写全量覆写式）。
**对外接口：** `load() -> list[dict]`（文件不存在返回空列表）、`save(records: list[dict])`。
**依赖：** 无。

### 后端 `job_routes.py`

**职责：** REST 接口。GET 列表；POST 生成 uuid4 + 校验后追加；PUT 按 id 替换（不存在 404）。
**对外接口：** `job_router`（FastAPI APIRouter）。
**依赖：** `job_storage`、`pydantic`。

### 前端 `JobProgressPage.tsx`

**职责：** 全量数据加载、派生显示列表、统计计算、组织子组件与新增/编辑提交刷新。
**对外接口：** 四个子组件的 props（见下）。
**依赖：** `api/jobClient.ts`、子组件。

### 前端 `api/jobClient.ts`

**职责：** 封装 `GET /jobs`、`POST /jobs`、`PUT /jobs/{id}`。
**对外接口：** `listJobs(): Promise<JobRecord[]>`、`createJob(data: JobPayload): Promise<JobRecord>`、`updateJob(id: string, data: JobPayload): Promise<JobRecord>`。
**依赖：** `types.ts`。

### 前端 `MetricCards.tsx`

**职责：** 渲染 5 张统计卡片。
**对外接口：** props `{ totals: number, total, active, offer, rejected, monthly }`。
**依赖：** 无。

### 前端 `JobToolbar.tsx`

**职责：** 搜索框（图标 + 防抖 300ms）、进度筛选下拉、排序下拉、导出 CSV 按钮。
**对外接口：** props `{ search, filter, sortDir, onSearchChange, onFilterChange, onSortChange, onExport }`。
**依赖：** `types.ts` 的 `JOB_STATUS` 常量数组。

### 前端 `JobTable.tsx`

**职责：** 表格 head/tbody、状态徽章渲染、编辑按钮、空状态。
**对外接口：** props `{ records: JobRecord[], onEdit(record) }`。
**依赖：** `JOB_STATUS_STYLE` 映射。

### 前端 `JobFormModal.tsx`

**职责：** 新增/编辑共享弹窗表单（input：company/position/applied_at/next_step/remark，select：status）。
**对外接口：** props `{ mode: "create" | "edit", initial: JobRecord | null, onClose(), onSubmit(payload) }`。
**依赖：** 无。

## 模块交互

```
进入页面（view === "progress"）
  └─ JobPage
       ├─ 挂载 → jobClient.listJobs() → jobs state
       ├─ 派生 displayed = 搜索+筛选过滤 → 按 applied_at 排序
       ├─ 派生 counts = {total, active(简历已投递/评估中), offer, rejected, monthly(本月)}
       ├─ MetricCards(counts)
       ├─ JobToolbar(search/filter/sort/onExport)
       │     └─ 导出：displayed → CSV → Blob 带 BOM → <a download>
       ├─ JobTable(displayed, onEdit) —— 含空状态
       └─ JobFormModal（create/edit 共用）
             └─ onSubmit → createJob/updateJob → 刷新 jobs → 关闭弹窗
```

## 文件组织

```
frontend/src/
├── api/jobClient.ts            # 新建：投递记录 API 客户端
├── types.ts                    # 修改：JobStatus、JobRecord
├── components/MainArea.tsx     # 修改：case "progress" 渲染 JobPage
└── components/JobProgress/
    ├── JobProgressPage.tsx     # 新建：页面主组件
    ├── MetricCards.tsx         # 新建：5 张统计卡片
    ├── JobToolbar.tsx          # 新建：搜索/筛选/排序/导出
    ├── JobTable.tsx            # 新建：表格 + 徽章 + 编辑 + 空状态
    └── JobFormModal.tsx        # 新建：新增/编辑弹窗

src/
├── api/job_storage.py          # 新建：data/jobs.json 读写
├── api/job_routes.py           # 新建：REST 路由
├── api/routes.py               # 修改：include job_router

data/jobs.json                  # 运行时生成，不入库

docs/投递进度/
├── spec.md                     # 已生成
├── plan.md                     # 本
├── task.md                     # 下一阶段
└── checklist.md                # 下一阶段
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 存储位置 | `data/jobs.json` 单 JSON 数组 | 数据量小，与个人信息单文件模式一致 |
| 搜索/统计/CSV 位置 | 前端 | 一次全量拉取后浏览器端过滤，后端保持纯持久层 |
| 新增/编辑弹窗 | 共享 `JobFormModal`，mode 区分 | 字段完全一致，避免重复 |
| 前端状态 | 组件内 state，不用 Context | 页面自包含、无跨页共享 |
| CSV 编码 | UTF-8 with BOM | Excel 打开中文不乱码 |
| 防抖 | 搜索输入防抖 300ms | 避免每次击键触发过滤（数据量小时仍合理） |
| ID 生成 | 后端 uuid4 | 幂等、稳定排序 |