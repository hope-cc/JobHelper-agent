# 投递进度管理 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/api/job_storage.py` | `data/jobs.json` 读写 |
| 新建 | `src/api/job_routes.py` | REST 路由（GET/POST/PUT） |
| 修改 | `src/api/routes.py` | include `job_router` |
| 修改 | `frontend/src/types.ts` | `JobStatus`、`JobRecord`、`JobPayload` |
| 新建 | `frontend/src/api/jobClient.ts` | list/create/update API 客户端 |
| 新建 | `frontend/src/components/JobProgress/MetricCards.tsx` | 5 张统计卡片 |
| 新建 | `frontend/src/components/JobProgress/JobToolbar.tsx` | 搜索/筛选/排序/导出 |
| 新建 | `frontend/src/components/JobProgress/JobTable.tsx` | 表格+徽章+编辑+空状态 |
| 新建 | `frontend/src/components/JobProgress/JobFormModal.tsx` | 新增/编辑弹窗 |
| 新建 | `frontend/src/components/JobProgress/JobProgressPage.tsx` | 页面主组件（组合 + 数据流） |
| 修改 | `frontend/src/components/MainArea.tsx` | `case "progress"` 渲染 JobPage |

## T1: 后端存储层

**文件：** `src/api/job_storage.py`
**依赖：** 无
**步骤：**
1. 定义 `DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "jobs.json"`
2. 实现 `load() -> list`：文件不存在返回 `[]`；存在则 `json.loads` 读取数组
3. 实现 `save(records: list) -> None`：`DATA_FILE.parent.mkdir(parents=True, exist_ok=True)` 后以 UTF-8 覆写（`ensure_ascii=False, indent=2`）
4. 文件顶部 docstring 说明单一 JSON 数组、全量覆写

**验证：** `D:\coding\Anaconda\envs\agent\python.exe -c "import sys; sys.path.insert(0,'.'); from src.api.job_storage import load, save; save([{'id':'x'}]); print(load()); import os; os.remove('data/jobs.json')"` 输出 `[{'id': 'x'}]`

## T2: 后端路由与校验

**文件：** `src/api/job_routes.py`
**依赖：** T1
**步骤：**
1. 定义 `JobRecordBody(BaseModel)`：`company: str`（min_length=1）、`position: str`（min_length=1）、`applied_at: str`、`status: str`、`next_step: str`、`remark: str = ""`
2. `applied_at` 用 `field_validator` 校验正则 `^\d{4}-\d{2}-\d{2}$`
3. `status` 用 `field_validator` 校验在 `{"简历已投递","评估中","Offer","已拒绝"}` 中
4. GET `/jobs`：返回 `{"jobs": job_storage.load()}`
5. POST `/jobs`：`uuid4` 生成 id，构造完整记录 `{**body.model_dump(), "id": str(uuid4())}`，追加后 save，返回记录
6. PUT `/jobs/{job_id}`：`load()` 后按 id 定位，找不到返回 404；找到则用新字段替换（保留 id），save 后返回新记录
7. 导出 `job_router = APIRouter()`

**验证：** 先临时在路由文件底部加 `if __name__ == "__main__":` 手测不可行——改为：启动后端 `python run.py`，用 curl 依次执行 GET/POST/PUT：
```bash
curl -s http://localhost:8000/api/jobs
curl -s -X POST http://localhost:8000/api/jobs -H "Content-Type: application/json" -d '{"company":"字节","position":"后端","applied_at":"2026-08-23","status":"评估中","next_step":"","remark":""}'
```
POST 返回含 id 的记录；最后 curl `-X PUT http://localhost:8000/api/jobs/<id>` 修改 status 验证更新成功
> 手动流程不便时，写临时脚本用 `httpx`（或 requests）走完三连请求即可

## T3: 挂载路由

**文件：** `src/api/routes.py`
**依赖：** T2（T2 完成即可挂，本身不依赖 T2 通过）
**步骤：**
1. `from src.api.job_routes import job_router`
2. 在 `router.include_router(resume_router)` 下一行加 `router.include_router(job_router)`
3. 校验 `/api/jobs` 可达：启动后端后 curl 返回 `{"jobs": []}`

**验证：** 启动后端 `python run.py`，`curl http://localhost:8000/api/jobs` 返回 200 与 `{"jobs": [...]}`

## T4: 前端类型与 API client

**文件：** `frontend/src/types.ts`、`frontend/src/api/jobClient.ts`
**依赖：** T3
**步骤：**
1. types.ts 末尾追加：
   ```ts
   export type JobStatus = "简历已投递" | "评估中" | "Offer" | "已拒绝";
   export interface JobRecord { id: string; company: string; position: string; applied_at: string; status: JobStatus; next_step: string; remark: string; }
   export type JobPayload = Omit<JobRecord, "id">;
   export const JOB_STATUSES: JobStatus[] = ["简历已投递", "评估中", "Offer", "已拒绝"];
   ```
2. jobClient.ts：
   - `listJobs(): Promise<JobRecord[]>` → GET `/api/jobs`，取 `res.json().jobs`
   - `createJob(payload): Promise<JobRecord>` → POST，body JSON
   - `updateJob(id, payload): Promise<JobRecord>` → PUT `/api/jobs/${id}`
   - 失败统一 `throw new Error(\`...\`)`

**验证：** `cd frontend && npx tsc --noEmit` 无类型错误

## T5: 统计卡片 MetricCards

**文件：** `frontend/src/components/JobProgress/MetricCards.tsx`
**依赖：** T4
**步骤：**
1. props：`{ total, active, offer, rejected, monthly }: { total: number; active: number; offer: number; rejected: number; monthly: number }`
2. 定义一个本地 `items` 数组：`[{label:"全部记录", value:total, accent:true}, {label:"进行中", value:active}, {label:"已获 Offer", value:offer}, {label:"已拒绝", value:rejected}, {label:"本月投递", value:monthly}]`
3. 渲染 `<div className="grid grid-cols-5 gap-4">`，每张卡 `bg-white rounded-2xl border border-slate-200 shadow-sm px-5 py-4`
4. 数值 `font-bold text-3xl`，第一张用 `text-blue-600`，其余 `text-slate-900`；label `text-sm text-slate-500 mt-1`

**验证：** `npx tsc --noEmit` 通过；视觉烧录（前端 dev 时）确认 5 张卡片网格排布

## T6: 工具栏 JobToolbar（搜索/筛选/排序/导出）

**文件：** `frontend/src/components/JobProgress/JobToolbar.tsx`
**依赖：** T4
**步骤：**
1. props：`{ search, filter, sortDir, onSearchChange, onFilterChange, onSortChange, onExport }: {...}`
2. 搜索输入框：外层 div `relative`，内部 SVG 搜索图标绝对定位左侧 `left-3`，input `pl-10`、占位符「搜索公司、岗位或备注...」、className 含 `w-[45%]`
3. 搜索框防抖：组件内 `useState` 本地值，`useEffect` 里 `setTimeout(300ms)` 后才调 `onSearchChange`（初始不触发）
4. 两个下拉：`全部进度 ▾`（`<select>`，值为四个状态 + 空串表示全部）、`时间: 新到旧 ▾`（两个选项「时间: 新到旧」/「时间: 旧到新」）
5. 导出按钮：`bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg px-4 py-2`，点击 `onExport()`

**验证：** `npx tsc --noEmit` 通过

## T7: 数据表格 JobTable

**文件：** `frontend/src/components/JobProgress/JobTable.tsx`
**依赖：** T4
**步骤：**
1. props `{ records, onEdit }`
2. thead：`bg-slate-50 text-slate-500 text-left text-xs font-medium`，列头`时间|公司|岗位|进度|下一步|操作`
3. tbody `divide-y divide-slate-100`，行 `hover:bg-slate-50 transition-colors`
4. 进度「徽章」（`JOB_STATUS_STYLE` 本地映射，见 plan）：
   ```tsx
   <span className={`inline-block rounded-full px-3 py-1 text-xs font-medium border ${JOB_STATUS_STYLE[rec.status]}`}>{rec.status}</span>
   ```
5. 公司格 `font-semibold text-slate-800`
6. 操作列编辑按钮：`text-blue-600 hover:underline text-sm`，`onClick={() => onEdit(rec)}`
7. records 为空时渲染空状态：`text-slate-400 text-center py-16`「暂无投递记录，点击右上角新增」

**验证：** `npx tsc --noEmit` 通过

## Task 8: 弹窗 JobFormModal

**文件：** `frontend/src/components/JobProgress/JobFormModal.tsx`
**依赖：** T4
**步骤：**
1. props `{ mode, initial, onClose, onSubmit }: { mode: "create" | "edit"; initial: JobRecord | null; onClose(): void; onSubmit(payload: JobPayload): void }`
2. 外层：固定遮罩 `fixed inset-0 bg-black/40 flex items-center justify-center z-50`，内部卡片 `bg-white rounded-2xl p-6 w-full max-w-md shadow-xl`
3. 表单字段 layout（网格 label + input，`space-y-4`）：
   - 公司：`input` type text required
   - 岗位：`input` text required
   - 投递时间：`input type="date"` required，值 `initial?.applied_at ?? today(YYYY-MM-DD)`
   - 进度：`select` required，四个状态
   - 下一步：`input` text
   - 备注：`input` / `textarea` text
4. 底部按钮行 `flex justify-end gap-2`：取消（`bg-slate-100`）、保存（`bg-blue-600 text-white`）
5. `onSubmit` 里组装 `JobPayload`，注意三个必填都有了再提
6. 初始化 state 用 `initial ?? 空`；取消或遮罩点击调 `onClose()`

**验证：** `npx tsc --noEmit` 通过

## Task 9: 主页面 JobProgressPage 与组装

**文件：** `frontend/src/components/JobProgress/JobProgressPage.tsx`
**依赖：** T6, T7, T8（全部子组件）
**步骤：**
1. 状态：`jobs: JobRecord[]`、`search`、`filter: JobStatus | "全部"`、`sortDir: "desc" | "asc"`、`modal: {mode, initial} | null`
2. 挂载 `useEffect`：`listJobs().then(setJobs)`
3. 派生 `const displayed = useMemo(...)`：先按搜索词匹配 company/position/remark（`toLowerCase` includes），再按 `filter`，最后按 `applied_at`（字符串比较）+ id 稳定排序
4. 派生 `counts`：total=jobs.length；active=status∈{简历已投递,评估中}；offer=status==="Offer"；rejected=status==="已拒绝"；monthly=当月 `YYYY-MM` 前缀 == 今天
5. 处理函数：`handleCreate(payload)` → `createJob().then(刷新)`；`handleUpdate(payload)` → `updateJob(modal.initial.id, payload).then(刷新)`；`handleExport()` 构造 CSV（表头「时间,公司,岗位,进度,下一步,备注」+ 行，Blob 加 `\uFEFF`，`URL.createObjectURL` + `<a download="投递记录.csv">`）
6. 渲染顺序：Header（小副标/主标题/描述 + 右上新增按钮）→ MetricCards → 白色大卡片（标题+提示 + Toolbar + Table）+ 弹窗

**验证：** `npx tsc --noEmit` + dev server 手动过一遍：新增→刷新→编辑→搜索→筛选→排序→导出

## Task 10: 挂载 MainArea

**文件：** `frontend/src/components/MainArea.tsx`
**依赖：** Task 9
**步骤：**
1. `import JobProgressPage from "./JobProgress/JobProgressPage";`
2. `case "progress":` 渲染 `<JobProgressPage />` 替换 `PlaceholderPage`

**验证：** `npx tsc --noEmit` 通过；dev server 侧边栏点「投递进度」进入真实页面

## 执行顺序

```
T1 → T2 → T3 → T4 → T6 ─┐
                         ├→ T9 → T10
                   T5 → T7 → T8 ─┘
```
（T5/T6//T8 各自依赖 T4，可并行或按序；T9 等全部完成）