# 投递进度-新增行业字段与分页 Plan

## 架构概览

沿用现有「前端 React 单页 + 后端 FastAPI + JSON 文件持久化」的投递进度模块架构，做三处增量：

1. **数据层（后端）**：为记录增加 `industry` 字段；`job_storage.load()` 在读取时对旧记录补默认值，保证前端拿到的 `industry` 恒为字符串。
2. **类型层（前端）**：`types.ts` 的 `JobRecord` / `JobPayload` 增加 `industry`。
3. **表现层（前端）**：表单加「行业」输入框、表格加「行业」列、CSV 导出加「行业」列；并在 `JobProgressPage` 加入客户端分页（每页 15 条）及分页控件组件。

分页沿用现有"全量加载 + 前端过滤"模式，不引入服务端分页；统计卡片与「共 N 条」基于过滤后全量计算，不受分页影响。

## 核心数据结构

### JobRecord（前端 types.ts，新增字段）

```
interface JobRecord {
  id: string;
  company: string;   // 必填
  position: string;  // 必填
  industry: string;  // 选填，默认 ""
  applied_at: string;
  status: JobStatus;
  next_step: string;
  remark: string;
}
```

`JobPayload = Omit<JobRecord, "id">` 自动继承 `industry`。

### JobRecordBody（后端 job_routes.py，新增字段）

```
class JobRecordBody(BaseModel):
    company: str
    position: str
    industry: str = ""   # 新增，选填
    applied_at: str
    status: str
    next_step: str = ""
    remark: str = ""
```

## 模块设计

### 后端存储 job_storage
**职责：** JSON 文件读写。`load()` 返回时对每条记录补齐缺失字段 `industry`（默认为 `""`），兼容旧数据。

**对外接口：** `load() -> list`、`save(records) -> None`（不变）。

### 后端路由 job_routes
**职责：** 增改查。`JobRecordBody` 增加 `industry` 字段（缺省 `""`），`model_dump()` 自动带上该字段。新增/更新时不需额外逻辑。

### 前端表单 JobFormModal
**职责：** 新增/编辑表单。增加「行业」自由文本输入框（选填），state 初始化自 `initial?.industry ?? ""`，提交时并入 payload；`edit` 模式下旧记录无值则显示空。

### 前端表格 JobTable
**职责：** 渲染列表。在「岗位」与「进度」之间新增「行业」列，空值显示「—」。

### 前端分页控件 Pagination（新建）
**职责：** 渲染上一页/下一页按钮与「第 x / y 页」信息。纯受控组件，props：`page`、`totalPages`、`onPageChange`。仅一页时禁用按钮（仍显示共几页，或隐藏——以需求「仅一页时隐藏/禁用均可」宽松处理，采用：仅一页时隐藏控件）。

### 前端页面 JobProgressPage
**职责：** 状态编排。新增 `page` state；基于过滤+排序后的 `displayed` 计算总页数、当前有效页、当前页切片，传给 `JobTable` 与 `Pagination`。CSV 导出列增加「行业」。页首「共 N 条」仍用 `displayed.length`。

## 模块交互（数据流）

```
listJobs() 载入 jobs（后端 load() 已补齐 industry）
    → displayed = 搜索 + 进度筛选 + 时间排序（全量）
    → counts（统计卡片，全量）
    → totalPages = max(1, ceil(displayed.length / 15))
    → effectivePage = min(max(page,1), totalPages)      // 页码自动 clamp，防空页
    → pageItems = displayed.slice((effectivePage-1)*15, effectivePage*15)
    → JobTable(records=pageItems) + Pagination(page=effectivePage, totalPages)
新增/编辑提交 → createJob/updateJob → setJobs 更新 → displayed 重算 → 页码 clamp 生效
```

页码 clamp 采用「派生 effectivePage」方案：不写副作用 useEffect，直接在渲染时计算，天然避免"筛选后页码越界出现空白页"。翻页操作用 `setPage` 记录意图，渲染时再 clamp。

## 文件组织

```
src/api/job_storage.py                 — load() 补齐 industry 默认值
src/api/job_routes.py                  — JobRecordBody 增加 industry
frontend/src/types.ts                  — JobRecord/JobPayload 增加 industry
frontend/src/components/JobProgress/JobFormModal.tsx     — 行业输入框
frontend/src/components/JobProgress/JobTable.tsx         — 行业列（空值占位）
frontend/src/components/JobProgress/Pagination.tsx       — 新建分页控件
frontend/src/components/JobProgress/JobProgressPage.tsx  — 分页编排 + CSV 行业列
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 旧记录 industry 兼容 | `job_storage.load()` 返回前补齐 `industry=""` | 一处归一化，前端/路由一律拿到字符串，避免 `undefined` 判断分散各处 |
| 分页位置 | 前端客户端分页（listJobs 仍返回全量） | 沿用现有全量加载 + 前端过滤模式，改动最小，当前数据量小 |
| 页码越界处理 | 渲染时派生 `effectivePage = clamp(page)` | 无副作用、逻辑简单，天然避免筛选后空页 |
| 分页控件形态 | 独立受控组件 Pagination | 职责单一，便于复用与测试；仅一页时隐藏 |
| 行业输入 | 自由文本 input | 用户已选定，实现最简单 |
| CSV 导出行列 | 列插入「行业」于岗位与进度之间，空值导出空串 | 与表格列序、需求 F6 一致 |
| 统计/「共 N 条」 | 基于过滤后全量 | 需求 F5 明确不受分页影响 |
