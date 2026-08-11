# 个人信息管理 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/api/profile_storage.py` | `data/personal/profile.json` 读写 |
| 新建 | `src/api/profile_routes.py` | `GET/PUT /api/personal` 路由 |
| 修改 | `src/api/routes.py` | 挂载 `profile_router` |
| 修改 | `frontend/src/types.ts` | 新增 `PersonalProfile` 等类型 |
| 新建 | `frontend/src/api/profileClient.ts` | `getPersonal` / `savePersonal` |
| 新建 | `frontend/src/components/profile/profileFieldConfigs.ts` | 字段配置（新增字段入口） |
| 新建 | `frontend/src/components/profile/SectionCard.tsx` | 分区卡片容器 |
| 新建 | `frontend/src/components/ProfileContext.tsx` | 表单状态 reducer |
| 新建 | `frontend/src/components/profile/BasicInfoSection.tsx` | 基本信息分区 |
| 新建 | `frontend/src/components/profile/EntrySection.tsx` | 通用条目分区 |
| 新建 | `frontend/src/components/profile/SelfEvaluationSection.tsx` | 自我评价分区 |
| 新建 | `frontend/src/components/ProfilePage.tsx` | 页面入口 + 保存按钮 |
| 修改 | `frontend/src/components/MainArea.tsx` | `profile` view → `ProfilePage` |

## T1: 后端存储层

**文件：** `src/api/profile_storage.py`
**依赖：** 无
**步骤：**
1. `DATA_DIR = data/personal`，`PROFILE_FILE = DATA_DIR / "profile.json"`
2. `empty_profile()` 返回空默认字典（七个分区键，经历类为空数组，基本信息字段为空字符串，`self_evaluation` 为空字符串）
3. `load()` 读取 JSON 返回 dict；文件不存在返回 None
4. `save(data)` 确保目录存在、写入 JSON（`ensure_ascii=False, indent=2`）

**验证：** 用 python 调用 `empty_profile()`、`save()`、`load()`，确认文件生成且可读回

## T2: 后端路由

**文件：** `src/api/profile_routes.py`、`src/api/routes.py`
**依赖：** T1
**步骤：**
1. `profile_routes.py`：`GET /api/personal` 返回 `load()` 或 `empty_profile()`；`PUT /api/personal` 接收 `dict`（pydantic `Body`），`save()` 后返回 `200`
2. `routes.py`：`router.include_router(profile_router)`
3. 用 pydantic `BaseModel` 定义请求体类型（同 `resume_routes` 的写法）

**验证：** 启动后端，`curl -X PUT /api/personal -d '{"basic_info":{...},...}'` 后 `GET` 能读回；`data/personal/profile.json` 生成

## T3: 前端类型

**文件：** `frontend/src/types.ts`
**依赖：** 无
**步骤：**
1. 新增 `BasicInfo`、`EducationEntry`、`InternshipEntry`、`ProjectEntry`、`AwardEntry`、`LanguageEntry`、`PersonalProfile`（结构与 plan.md 一致，条目含 `id: string`）

**验证：** `npx tsc --noEmit` 无类型错误

## T4: 前端 API 客户端

**文件：** `frontend/src/api/profileClient.ts`
**依赖：** T3
**步骤：**
1. `getPersonal()`：`GET /api/personal`，返回 `PersonalProfile`
2. `savePersonal(data)`：`PUT /api/personal`，`Content-Type: application/json`，失败抛错

**验证：** `npx tsc --noEmit` 无类型错误

## T5: 字段配置与通用 UI 组件

**文件：** `frontend/src/components/profile/profileFieldConfigs.ts`、`frontend/src/components/profile/SectionCard.tsx`
**依赖：** T3（配置中的 key 对应类型字段）
**步骤：**
1. 定义 `ProfileFieldConfig` 类型；导出 `BASIC_INFO_FIELDS`、`EDUCATION_FIELDS`、`INTERNSHIP_FIELDS`、`PROJECT_FIELDS`、`AWARD_FIELDS`、`LANGUAGE_FIELDS` 六个配置数组（key/label/type/options/span 按 spec 分区字段）
2. `SectionCard`：`title`、`onAdd?`、`addLabel?`、`children` 的卡片容器，标题行右侧渲染「添加」按钮

**验证：** `npx tsc --noEmit` 无类型错误

## T6: 表单状态 Context

**文件：** `frontend/src/components/ProfileContext.tsx`
**依赖：** T3
**步骤：**
1. `initialState`：`emptyProfile()`（含一条空 entry 用于初始展示，或空数组——按 spec 设计：初始为空数组，用户点「添加」才出现条目）
2. reducer actions：`LOAD_PROFILE`、`SET_BASIC_FIELD`、`ADD_ENTRY`、`SET_ENTRY_FIELD`、`DELETE_ENTRY`、`SET_SELF_EVAL`
3. `ADD_ENTRY` 接收分区 key（education/internship/project/award/language）与一条新 entry（含新生成的 `id`）；`SET_ENTRY_FIELD` 接收分区 key、entry id、字段 key、值
4. 导出 `ProfileProvider` / `useProfileState` / `useProfileDispatch`

**验证：** `npx tsc --noEmit` 无类型错误

## T7: 分区组件

**文件：** `frontend/src/components/profile/BasicInfoSection.tsx`、`EntrySection.tsx`、`SelfEvaluationSection.tsx`
**依赖：** T5、T6
**步骤：**
1. `BasicInfoSection`：遍历 `BASIC_INFO_FIELDS` 渲染输入（text / select），dispatch `SET_BASIC_FIELD`
2. `EntrySection`：props 接收分区 key、条目数组、字段配置、标题；渲染条目列表（只读摘要 + 编辑/删除按钮）+「添加」时展开空表单；字段编辑 dispatch `SET_ENTRY_FIELD`；删除 dispatch `DELETE_ENTRY`
3. `SelfEvaluationSection`：多行文本框，dispatch `SET_SELF_EVAL`

**验证：** `npx tsc --noEmit` 无类型错误

## T8: 页面入口与导航接入

**文件：** `frontend/src/components/ProfilePage.tsx`、`frontend/src/components/MainArea.tsx`
**依赖：** T4、T6、T7
**步骤：**
1. `ProfilePage`：`ProfileProvider` 包裹；挂载时 `getPersonal()` → `LOAD_PROFILE`；渲染「保存」按钮 + 七个分区；保存时从 state 构建字典（条目剥离 `id`）→ `savePersonal()` → 成功/失败提示（简单状态文本或 alert）
2. `MainArea`：`profile` 分支改为渲染 `<ProfilePage />`

**验证：** `npx tsc --noEmit` + `npx vite build` 通过；启动前后端，进入页面可填写、添加条目、保存、刷新回填

## 执行顺序

```
T1 → T2
       T3 → T5 → T6 → T7
       T3 → T4 ──→ T8
```
