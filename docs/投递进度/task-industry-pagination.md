# 投递进度-新增行业字段与分页 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/api/job_storage.py` | `load()` 补齐 `industry` 默认值 |
| 修改 | `src/api/job_routes.py` | `JobRecordBody` 增加 `industry` 字段 |
| 修改 | `frontend/src/types.ts` | `JobRecord` 增加 `industry` |
| 修改 | `frontend/src/components/JobProgress/JobFormModal.tsx` | 表单增加「行业」输入框 |
| 修改 | `frontend/src/components/JobProgress/JobTable.tsx` | 表格增加「行业」列 |
| 新建 | `frontend/src/components/JobProgress/Pagination.tsx` | 分页控件 |
| 修改 | `frontend/src/components/JobProgress/JobProgressPage.tsx` | 分页编排 + CSV 加行业列 |

## T1: 后端存储兼容 industry

**文件：** `src/api/job_storage.py`
**依赖：** 无
**步骤：**
1. 在 `load()` 函数读取记录后，对每条记录补齐缺失字段 `industry`（缺失则设 `""`）。
2. 保持 `save()` 不变。

**验证：** 用现有 `data/jobs.json`（旧记录无 industry）调用 `load()`，断言每条记录都有 `industry` 且值为 `""`；原有字段值不变。

## T2: 后端路由增加 industry 字段

**文件：** `src/api/job_routes.py`
**依赖：** 无（与 T1 无强依赖，可并行）
**步骤：**
1. `JobRecordBody` 增加字段 `industry: str = ""`。
2. 新增/更新接口无需改逻辑，`model_dump()` 自动带上 `industry`。

**验证：** POST 一条含 `industry` 的记录，返回及落库 JSON 含该字段；不传 `industry` 时缺省 `""`。

## T3: 前端类型增加 industry

**文件：** `frontend/src/types.ts`
**依赖：** 无
**步骤：**
1. `JobRecord` 接口增加 `industry: string; // 选填`。
2. `JobPayload = Omit<JobRecord, "id">` 无需改动，自动继承。

**验证：** `tsc`（或前端构建）通过，`JobPayload` 类型包含 `industry`。

## T4: 表单增加「行业」输入框

**文件：** `frontend/src/components/JobProgress/JobFormModal.tsx`
**依赖：** T3
**步骤：**
1. 新增 state `industry`，初始化为 `initial?.industry ?? ""`。
2. 在表单（如「下一步」之前或「岗位」下方）增加一个选填输入框「行业」，值为 `industry`，onChange 更新。
3. `handleSubmit` 提交 payload 中加入 `industry: industry.trim()`。
4. 公司/岗位必填校验逻辑保持不变。

**验证：** 打开新增表单可见「行业」输入框，填值保存后出现于提交 payload；打开编辑旧记录（无 industry）时输入框为空。

## T5: 表格增加「行业」列

**文件：** `frontend/src/components/JobProgress/JobTable.tsx`
**依赖：** T3
**步骤：**
1. 表头在「岗位」与「进度」之间插入 `<th>行业</th>`。
2. 行数据在「岗位」与「进度」单元格之间插入行业单元格：有值显示值，无值或空显示「—」。

**验证：** 表格列序为 时间|公司|岗位|行业|进度|下一步|操作；有/无行业值显示正确。

## T6: 新建分页控件

**文件：** `frontend/src/components/JobProgress/Pagination.tsx`（新建）
**依赖：** 无
**步骤：**
1. 定义 props：`page: number`、`totalPages: number`、`onPageChange: (p: number) => void`。
2. 渲染「上一页」「下一页」按钮与「第 x / y 页」文案。
3. 上一页禁用条件 `page <= 1`；下一页禁用条件 `page >= totalPages`。
4. 仅一页（`totalPages <= 1`）时返回 `null`（隐藏控件）。
5. 样式与现有 `slate` 系列按钮风格一致。

**验证：** 多页时按钮可翻页、边界正确禁用；单页时不渲染。

## T7: 页面分页编排 + CSV 行业列

**文件：** `frontend/src/components/JobProgress/JobProgressPage.tsx`
**依赖：** T5、T6
**步骤：**
1. 定义分页常量 `PAGE_SIZE = 15`。
2. 新增 state `page`（初始 1）。
3. 基于 `displayed` 计算：`totalPages = Math.max(1, Math.ceil(displayed.length / PAGE_SIZE))`；`effectivePage = Math.min(Math.max(page, 1), totalPages)`；`pageItems = displayed.slice((effectivePage - 1) * PAGE_SIZE, effectivePage * PAGE_SIZE)`。
4. `JobTable` 传入 `records={pageItems}`；条件渲染 `<Pagination page={effectivePage} totalPages={totalPages} onPageChange={setPage} />`（仅 `totalPages > 1` 时渲染）。
5. `CSV_HEADER` 常量改为 `["时间","公司","岗位","行业","进度","下一步","备注"]`。
6. 导出行映射在岗位与进度之间插入 `rec.industry`。
7. 页首「共 N 条」保持 `displayed.length`。

**验证：** 记录 >15 条时分页生效；有筛选时「共 N 条」与统计卡片不变；导出 CSV 含「行业」列。

## 执行顺序

```
T1 ──┐
T2 ──┼─►（可并行）► T3 ─► T4 ─► T5 ─► T7
T3 ──┘                   T6 ─► T7
```
（T4/T5/T6 依赖 T3，可并行；T7 依赖 T5/T6）
