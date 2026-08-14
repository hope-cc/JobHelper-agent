# 个人信息管理-字段自定义 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `frontend/src/types.ts` | 删实习/项目类型、basic_info 改动态键、新增 BasicFieldSchema |
| 修改 | `frontend/src/components/profile/profileFieldConfigs.ts` | DEFAULT_BASIC_FIELDS、删实习/项目字段配置、sanitizeFieldKey、emptyProfile |
| 修改 | `frontend/src/components/ProfileContext.tsx` | 新增 4 个 schema 相关 reducer 动作 |
| 修改 | `frontend/src/components/profile/BasicInfoSection.tsx` | 按 schema 渲染 + 增删改/排序 UI |
| 修改 | `frontend/src/components/ProfilePage.tsx` | 删实习/项目分区、更新 toStateProfile/toSavableProfile |
| 修改 | `src/api/profile_storage.py` | empty_profile 新结构、load 剥离遗留键 |
| 修改 | `src/api/profile_routes.py` | PersonalProfileBody 更新 |
| 不变 | `src/tools/builtin/get_personal_info.py` | 零改动 |

## T1: 前端类型改造

**文件：** `frontend/src/types.ts`
**依赖：** 无
**步骤：**
1. 新增 `BasicFieldSchema` 接口：`{ key: string; label: string; type: "text"|"textarea"|"select"; options?: string[] }`。
2. 删除 `InternshipEntry`、`ProjectEntry` 接口。
3. `BasicInfo` 接口改为 `Record<string, string>`（或删除该接口，直接用 `Record`）。
4. `ProfileSectionKey` 收窄为 `"education" | "award" | "language"`；`ProfileEntry` 联合类型同步去掉 Internship/Project。
5. `PersonalProfile` 增加 `basic_fields_schema: BasicFieldSchema[]`，删除 `internship`/`project` 字段。
6. `SavableProfile` 同构更新。

**验证：** `cd frontend && npm run build` 中 `tsc -b` 能报出后续消费方需要同步（先接受报错，T2-T5 修完后再全量验证）；或在 IDE 中确认无语法错误。

## T2: 字段配置与键名工具

**文件：** `frontend/src/components/profile/profileFieldConfigs.ts`
**依赖：** T1
**步骤：**
1. `BASIC_INFO_FIELDS` 重命名为 `DEFAULT_BASIC_FIELDS`，导出作为默认 schema。
2. 删除 `INTERNSHIP_FIELDS`、`PROJECT_FIELDS`；保留 EDUCATION/AWARD/LANGUAGE。
3. `emptyBasicInfo()` 基于 `DEFAULT_BASIC_FIELDS` 生成空值字典。
4. `emptyProfile()`：`basic_fields_schema: DEFAULT_BASIC_FIELDS`（深拷贝）、`basic_info: emptyBasicInfo()`、`education/award/language: []`、`self_evaluation: ""`、`masked_basic_fields: []`。
5. 新增 `sanitizeFieldKey(label: string, existingKeys: string[]): string`：清洗 `.`/空白/换行→`_`，与 existingKeys 冲突时追加 `_2`、`_3`。

**验证：** `cd frontend && npm run build`（tsc 仅剩 T3-T5 的报错）。

## T3: 状态管理新增动作

**文件：** `frontend/src/components/ProfileContext.tsx`
**依赖：** T1、T2
**步骤：**
1. `ProfileAction` 联合类型新增：
   - `{ type: "ADD_BASIC_FIELD"; schema: BasicFieldSchema }`
   - `{ type: "RENAME_BASIC_FIELD"; key: string; label: string }`
   - `{ type: "DELETE_BASIC_FIELD"; key: string }`
   - `{ type: "MOVE_BASIC_FIELD"; fromIndex: number; toIndex: number }`
2. reducer 新增对应 case：
   - ADD：`basic_fields_schema` 追加。
   - RENAME：schema 里匹配 key 的项改 label，key 不变。
   - DELETE：schema 过滤掉该 key；`basic_info` 删除该键；`masked_basic_fields` 过滤掉该键。
   - MOVE：数组 splice 移动。

**验证：** `cd frontend && npm run build`（tsc 仅剩 T4/T5 的报错）。

## T4: 基本信息区渲染与字段管理 UI

**文件：** `frontend/src/components/profile/BasicInfoSection.tsx`
**依赖：** T3
**步骤：**
1. 从 state 取 `basic_fields_schema`、`basic_info`、`masked_basic_fields`，遍历 schema 渲染字段（不再引用 `BASIC_INFO_FIELDS`）。
2. 每行：标签文本 + 铅笔图标（点击进入行内改名输入框，回车/失焦提交 `RENAME_BASIC_FIELD`）+ 脱敏勾选（`TOGGLE_MASKED_FIELD`）+ ✕ 删除（`DELETE_BASIC_FIELD`）+ 拖拽手柄。
3. 输入控件按 `field.type` 渲染：text → input；textarea → textarea；select → select（选项来自 `field.options`）。值读写用 `basic_info[field.key]`。
4. 「+ 添加字段」按钮展开小表单：标签 input、类型 select（单行文本/多行文本/下拉选择）、下拉时显示选项 input（逗号分隔）；确认时用 `sanitizeFieldKey(label, 现有键)` 生成键，dispatch `ADD_BASIC_FIELD`，并重置表单。
5. 排序：给字段行加 `draggable`，onDragStart 记 index、onDragOver preventDefault、onDrop 调 `MOVE_BASIC_FIELD(from, to)`。

**验证：** `cd frontend && npm run build` 通过（T1-T5 全量）；`npm run lint` 通过。

## T5: 页面主组件接入

**文件：** `frontend/src/components/ProfilePage.tsx`
**依赖：** T2、T4
**步骤：**
1. 删除「实习经历」「项目经历」两个 `EntrySection` 及其字段配置 import。
2. `toStateProfile`：`basic_fields_schema: saved.basic_fields_schema?.length ? saved.basic_fields_schema : DEFAULT_BASIC_FIELDS`；`basic_info: saved.basic_info ?? {}`；education/award/language 补 id；去掉 internship/project 映射。
3. `toSavableProfile`：带上 `basic_fields_schema`，去掉 internship/project。

**验证：** `cd frontend && npm run build` 通过、`npm run lint` 通过。

## T6: 后端存储模型

**文件：** `src/api/profile_storage.py`
**依赖：** 无（后端独立）
**步骤：**
1. `empty_profile()`：返回新结构——含 `basic_fields_schema`（10 个默认字段，键名与现状一致）、`basic_info` 全空、`education/award/language: []`、`self_evaluation: ""`、`masked_basic_fields: []`；去掉 `internship`/`project`。
2. `load()`：`json.loads` 后执行 `data.pop("internship", None)`、`data.pop("project", None)` 再返回。

**验证：** 运行 `D:/coding/Anaconda/envs/agent/python.exe -c "from src.api import profile_storage; print(profile_storage.empty_profile().keys()); import json; print(json.loads(json.dumps({'internship':[1],'project':[2],'award':[]}) ) )"` 之类的最小脚本；或直接跑 pytest（T8）。

## T7: 后端路由模型

**文件：** `src/api/profile_routes.py`
**依赖：** T6
**步骤：**
1. `PersonalProfileBody` 删除 `internship`、`project` 字段；新增 `basic_fields_schema: list = []`（放在 `basic_info` 之后）。
2. 其余不变。

**验证：** T8 的 pytest 全量通过。

## T8: 后端测试验证

**文件：** `tests/`（不改动）
**依赖：** T6、T7
**步骤：**
1. 在项目根目录运行 `D:/coding/Anaconda/envs/agent/python.exe -m pytest`。
2. 确认全部通过（含 browser_mcp 的取值/脱敏测试）。

**验证：** pytest 退出码 0，无失败。

## T9: 前端构建验证

**文件：** `frontend/`（已改）
**依赖：** T5
**步骤：**
1. `cd frontend && npm run build`。
2. `cd frontend && npm run lint`。

**验证：** 两条命令均通过无错误。

## 执行顺序
```
T1 → T2 → T3 → T4 → T5 ─┐
                          ├→ T9（前端构建/lint）
T6 → T7 ─────────────────┘
    ↘ T8（后端 pytest，可与 T1-T5 并行）
```
（T6/T7 后端与 T1-T5 前端无依赖，可并行；T8/T9 为两端最终验证。）
