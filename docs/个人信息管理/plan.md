# 个人信息管理 Plan

## 架构概览

三个模块：

1. **后端 API（FastAPI）**：`profile_storage.py` 负责读写 `data/personal/profile.json`；`profile_routes.py` 暴露 `GET /api/personal` 与 `PUT /api/personal`。不做任何业务逻辑，只做持久化与读取，契约就是「整份字典」。
2. **前端 API 客户端**：`frontend/src/api/profileClient.ts` 封装 `getPersonal()` / `savePersonal()` 两个请求。
3. **前端表单页（React）**：`ProfilePage` 用 `ProfileContext`（useReducer）维护整份表单状态，分区组件通过「字段配置」驱动渲染，避免五个经历类分区重复代码。

核心设计目标：**保存的字典 = 后续传给后端、agent 只读键的那个字典**。前端状态里为每条记录生成局部 `id`（用于 React key 与编辑/删除定位），保存前剥离，保证持久化字典干净、键稳定。

## 核心数据结构

### 字段配置（前端，驱动表单渲染）

```ts
interface ProfileFieldConfig {
  key: string;              // 字段键（英文 snake_case，即字典中的键）
  label: string;            // 显示标签（中文）
  type: "text" | "textarea" | "select";
  options?: string[];       // type=select 时的选项
  span?: boolean;           // 是否占满整行（如描述、自我评价）
}
```

各分区字段配置集中放在 `frontend/src/components/profile/profileFieldConfigs.ts`，**这是后续新增字段的唯一入口之一**。

### PersonalProfile（前端 types.ts 与后端持久化 JSON 结构一致）

```ts
interface BasicInfo {
  name: string; phone: string; email: string;
  gender: string; age: string; location: string;
  id_type: string; id_number: string; id_valid_until: string;
  hometown: string;
}
interface EducationEntry { id: string; start_time: string; end_time: string; school: string; degree: string; degree_type: string; major: string; }
interface InternshipEntry { id: string; start_time: string; end_time: string; company: string; position: string; description: string; }
interface ProjectEntry { id: string; start_time: string; end_time: string; name: string; role: string; link: string; description: string; }
interface AwardEntry { id: string; time: string; name: string; description: string; }
interface LanguageEntry { id: string; language: string; proficiency: string; }
interface PersonalProfile {
  basic_info: BasicInfo;
  education: EducationEntry[];
  internship: InternshipEntry[];
  project: ProjectEntry[];
  award: AwardEntry[];
  language: LanguageEntry[];
  self_evaluation: string;
}
```

持久化 JSON 与上述一致，但**条目不含 `id`**（保存前剥离），例如：

```json
{
  "basic_info": { "name": "张三", "phone": "", "email": "", "gender": "男", "age": "25", "location": "北京", "id_type": "身份证", "id_number": "", "id_valid_until": "", "hometown": "湖南" },
  "education": [ { "start_time": "2020-09", "end_time": "2024-06", "school": "XX大学", "degree": "本科", "degree_type": "统招", "major": "计算机科学" } ],
  "internship": [],
  "project": [],
  "award": [],
  "language": [],
  "self_evaluation": ""
}
```

### API（后端）

- `GET /api/personal` → 返回完整字典；无文件时返回空默认结构
- `PUT /api/personal` → 接收完整字典，覆写 `data/personal/profile.json`，返回成功

## 模块设计

### 后端 profile_storage.py
**职责：** `data/personal/profile.json` 的读写。
**对外接口：** `load() -> dict | None`、`save(data: dict) -> None`、`empty_profile() -> dict`。
**依赖：** 无（标准库）。

### 后端 profile_routes.py
**职责：** 暴露 `GET/PUT /api/personal`。
**对外接口：** `profile_router`（`APIRouter`）。
**依赖：** `profile_storage`。

### 前端 api/profileClient.ts
**职责：** 封装后端请求。
**对外接口：** `getPersonal(): Promise<PersonalProfile>`、`savePersonal(data: PersonalProfile): Promise<void>`。
**依赖：** `types.ts`。

### 前端 ProfileContext.tsx
**职责：** 用 reducer 维护 `PersonalProfile` 状态，提供加载、字段更新、条目增删改。
**对外接口：** `ProfileProvider`、`useProfileState()`、`useProfileDispatch()`。
**action：** `LOAD_PROFILE`、`SET_BASIC_FIELD`、`ADD_ENTRY`、`SET_ENTRY_FIELD`、`DELETE_ENTRY`、`SET_SELF_EVAL`。
**依赖：** `types.ts`。

### 前端 profileFieldConfigs.ts
**职责：** 定义 `ProfileFieldConfig` 类型与七个分区的字段配置数组（`BASIC_INFO_FIELDS` / `EDUCATION_FIELDS` / `INTERNSHIP_FIELDS` / `PROJECT_FIELDS` / `AWARD_FIELDS` / `LANGUAGE_FIELDS`）。
**依赖：** 无。

### 前端分区组件 components/profile/
- `SectionCard.tsx` — 分区卡片容器：标题 + 右侧「添加」按钮（可选）+ 内容。
- `BasicInfoSection.tsx` — 用 `BASIC_INFO_FIELDS` 配置渲染基本信息表单。
- `EntrySection.tsx` — 通用条目分区：渲染已添加条目列表 + 展开编辑表单 + 删除按钮；字段由传入的配置决定。五个经历类分区共用。
- `SelfEvaluationSection.tsx` — 自我评价多行文本框。

### 前端 ProfilePage.tsx
**职责：** 页面入口：挂载时 `getPersonal()` 回填；渲染七个分区 + 顶部「保存」按钮；保存时构建字典（剥离 id）→ `savePersonal()` → 成功/失败提示。

## 模块交互

```
用户进入「个人信息管理」 → ProfilePage 挂载
  → GET /api/personal → ProfileContext LOAD_PROFILE 回填
用户填写 / 增删条目 → 各分区 dispatch → Context 更新（不自动保存）
点「保存」→ ProfilePage 从 state 构建字典（剥离条目 id）
  → PUT /api/personal → 后端覆写 data/personal/profile.json → 返回成功 → 页面提示
重新进入页面 → 再次 GET 回填
```

## 文件组织

```
docs/个人信息管理/                       — 本期四份文档
data/personal/profile.json               — 运行后生成
src/api/
├── profile_storage.py                   — 新建：JSON 存储
└── profile_routes.py                    — 新建：GET/PUT 路由
src/api/routes.py                        — 修改：挂载 profile_router
frontend/src/
├── types.ts                             — 修改：新增 PersonalProfile 等类型
├── api/profileClient.ts                 — 新建：请求封装
└── components/
    ├── ProfileContext.tsx               — 新建：表单状态 reducer
    ├── ProfilePage.tsx                  — 新建：页面入口 + 保存按钮
    ├── profile/
    │   ├── profileFieldConfigs.ts       — 新建：字段配置（新增字段入口）
    │   ├── SectionCard.tsx              — 新建：分区卡片容器
    │   ├── BasicInfoSection.tsx         — 新建：基本信息分区
    │   ├── EntrySection.tsx             — 新建：通用条目分区
    │   └── SelfEvaluationSection.tsx    — 新建：自我评价分区
    └── MainArea.tsx                     — 修改：profile view → ProfilePage
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 键命名 | 英文 snake_case | 供 agent 只读键的程序化使用，稳定不变 |
| 存储格式 | 单 JSON 文件 `data/personal/profile.json` | 单份档案覆盖保存，简单 |
| API | `GET/PUT /api/personal`，整份字典 | 与「整份字典传入后端」工作流一致；PUT 语义匹配覆写 |
| 前端状态 | React Context + useReducer | 页面内跨分区共享，模式与 ResumeContext 一致 |
| 通用条目分区 | 字段配置驱动的 `EntrySection` | 5 个经历类分区共用一套增删改逻辑；新增字段只改配置 |
| 条目 id | 前端本地生成，保存时剥离 | React key 与编辑/删除需要稳定 id；持久化字典保持干净 |
| 保存时机 | 仅点击「保存」才提交，无自动保存 | 避免频繁写盘，需求明确要求「保存功能」 |
| 字段校验 | 不做格式校验 | 需求未要求，且后续 agent 填表前可能自行规整 |
