# 个人信息管理-字段自定义 Plan

## 架构概览
改动集中在「个人信息管理」单模块，跨前端（React）与后端（FastAPI）两层：

- **前端**：基本信息区从「代码写死字段」改为「由持久化的 `basic_fields_schema` 驱动渲染」，用户可增/删/改/排序字段；实习、项目两个分区及相关类型、reducer 动作删除。
- **后端**：仅调整 profile 的存取模型——`PersonalProfileBody` 与 `empty_profile()` 去掉 `internship`/`project`、新增 `basic_fields_schema`；`load()` 剥离历史遗留的实习/项目键，保证任何消费方（页面、LLM 工具）都读不到。
- **LLM 工具**：`getPersonalInfo` **零改动**——它 `json.dumps(data)` 返回整份档案，新增的 `basic_fields_schema` 会自动暴露给 LLM，键→标签映射天然可用；脱敏仍按 `masked_basic_fields` 键名匹配。

## 核心数据结构

### 持久化结构（data/personal/profile.json）
```json
{
  "basic_fields_schema": [
    { "key": "name", "label": "姓名", "type": "text" },
    { "key": "gender", "label": "性别", "type": "select", "options": ["男", "女", "其他"] },
    "...（其余预设字段）"
  ],
  "basic_info": { "name": "张三", "...": "..." },
  "education": [ { "start_time": "", "...": "" } ],
  "award": [ ... ],
  "language": [ ... ],
  "self_evaluation": "",
  "masked_basic_fields": ["email", "..."]
}
```
- `basic_fields_schema` 为字段元数据数组（键、标签、类型、选项、顺序=数组顺序），用户未改动时默认等于现有 10 个预设字段（键名与现状完全一致）。
- `basic_info` 为「键→值」字典，键与 schema 中的 `key` 一致。
- `internship`、`project` 两个键整体移除。

### 前端类型（frontend/src/types.ts）
```ts
export interface BasicFieldSchema {
  key: string;
  label: string;
  type: "text" | "textarea" | "select";
  options?: string[];
}

export interface PersonalProfile {
  basic_fields_schema: BasicFieldSchema[];
  basic_info: Record<string, string>;   // 原 BasicInfo 接口删除，改为动态键
  education: EducationEntry[];
  award: AwardEntry[];
  language: LanguageEntry[];
  self_evaluation: string;
  masked_basic_fields: string[];
}
```
- 删除 `InternshipEntry`、`ProjectEntry` 接口；`ProfileSectionKey` 收窄为 `"education" | "award" | "language"`；`ProfileEntry` 联合类型同步收窄。
- `SavableProfile` 与 `PersonalProfile` 同构（条目剥 id）。

### 键名生成规则（前端 helper）
- 输入：用户填写的标签 + 现有 schema 的键集合。
- 输出：稳定键。清洗 `.`、空白、换行等字符 → `_`；若与已有键重复，追加序号 `_2`、`_3`……；中文标签直接可用。
- 示例：`微信号` → 键 `微信号`；`我的.邮箱` → 键 `我的_邮箱`；重复 `邮箱` → `邮箱_2`。

## 模块设计

### 前端

#### types.ts（修改）
删除实习/项目相关类型，新增 `BasicFieldSchema`，`BasicInfo` 改为 `Record<string,string>`，更新 `PersonalProfile`/`SavableProfile`/`ProfileSectionKey`/`ProfileEntry`。

#### components/profile/profileFieldConfigs.ts（修改）
- `BASIC_INFO_FIELDS` 重命名为 `DEFAULT_BASIC_FIELDS`（作为默认/兜底 schema）。
- 删除 `INTERNSHIP_FIELDS`、`PROJECT_FIELDS`；保留 `EDUCATION_FIELDS`/`AWARD_FIELDS`/`LANGUAGE_FIELDS`。
- `emptyBasicInfo()`、`emptyProfile()` 改为基于 `DEFAULT_BASIC_FIELDS` 生成，并携带 `basic_fields_schema`。
- 新增 `sanitizeFieldKey(label, existingKeys)`：按上述规则生成键。

#### components/ProfileContext.tsx（修改）
新增 reducer 动作：
- `ADD_BASIC_FIELD { schema }` —— 追加到 `basic_fields_schema`。
- `RENAME_BASIC_FIELD { key, label }` —— 只改 label，不动 key。
- `DELETE_BASIC_FIELD { key }` —— 移除 schema 项、`basic_info[key]`、`masked_basic_fields` 中的该键。
- `MOVE_BASIC_FIELD { fromIndex, toIndex }` —— 调整 schema 数组顺序。
- 保留 `SET_BASIC_FIELD`、`TOGGLE_MASKED_FIELD` 等既有动作。

#### components/profile/BasicInfoSection.tsx（修改）
- 改为遍历 `basic_fields_schema` 渲染，不再引用写死的字段数组。
- 每行字段：标签、按 type 渲染的输入控件、脱敏勾选、改名（铅笔→行内输入）、删除（✕）、拖拽手柄。
- 底部「+ 添加字段」：行内展开小表单——标签、类型（单行/多行/下拉）、选项（选下拉时），确认后 `ADD_BASIC_FIELD`。
- 排序用**原生 HTML5 拖拽事件**（draggable + dragstart/dragover/drop），不引入第三方依赖（CLAUDE.md 要求装库前先提醒）。

#### components/ProfilePage.tsx（修改）
- 删除「实习经历」「项目经历」两个 `EntrySection`。
- `toStateProfile`：`basic_fields_schema` 有值则用、无则回退 `DEFAULT_BASIC_FIELDS`；`basic_info` 直接用字典；education/award/language 补 id。
- `toSavableProfile`：条目剥 id，带上 `basic_fields_schema`。

### 后端

#### src/api/profile_storage.py（修改）
- `empty_profile()`：新结构——含 `basic_fields_schema`（10 个默认字段）、移除 `internship`/`project`。
- `load()`：读取后 `pop` 掉 `internship`、`project` 两个历史遗留键，保证页面与 LLM 工具都读不到（F7）。
- `save()` 不变（覆写整份）。

#### src/api/profile_routes.py（修改）
- `PersonalProfileBody`：移除 `internship`、`project`；新增 `basic_fields_schema: list = []`。

#### src/tools/builtin/get_personal_info.py（不变）
读 `load()`（已剥离遗留键）→ 按 `masked_basic_fields` 脱敏 → 返回 JSON（自动带上 `basic_fields_schema`）。

## 模块交互
1. **加载**：GET `/api/personal` → `profile_storage.load()`（剥离遗留键，无则 `empty_profile()`）→ 前端 `toStateProfile` → reducer `LOAD_PROFILE`。
2. **编辑**：用户增删改/排序字段、填值、勾脱敏 → 各 reducer 动作更新内存 state。
3. **保存**：前端 `toSavableProfile` → PUT `/api/personal` → `PersonalProfileBody` 校验 → `profile_storage.save()` 覆写 JSON。
4. **LLM 读取**：`getPersonalInfo` → `load()` → 脱敏 → JSON（含 `basic_fields_schema`，LLM 以标签反查键）；`browser_fill_form` 收到 `basic_info.<key>` 时按 `.` 分路径取值、按键名脱敏。

## 文件组织
```
frontend/src/
├── types.ts                                  修改
├── components/ProfilePage.tsx                修改
├── components/ProfileContext.tsx             修改
└── components/profile/
    ├── profileFieldConfigs.ts                修改
    ├── BasicInfoSection.tsx                  修改
    ├── EntrySection.tsx                      不变
    ├── SelfEvaluationSection.tsx             不变
    └── SectionCard.tsx                       不变
src/
├── api/profile_storage.py                    修改
├── api/profile_routes.py                     修改
└── tools/builtin/get_personal_info.py        不变
tests/（browser_mcp 既有测试）                 不变，须全部通过
```

## 技术决策
| 决策点 | 选择 | 理由 |
|--------|------|------|
| 字段元数据存哪 | profile.json 内新增 `basic_fields_schema` 键 | 单文件无新存储；`getPersonalInfo` 自动暴露给 LLM（N5） |
| 键名生成 | 前端按标签生成，清洗路径非法字符、重名加序号；中文键可用 | 已实测 Python/JSON/路径解析/脱敏全兼容；键可读、可猜、稳定 |
| 排序实现 | 原生 HTML5 拖拽，不引依赖 | 避免新增 npm 依赖；场景简单，一个分区内拖动 |
| 脱敏标记存哪 | 仍用 `masked_basic_fields` 键名列表，不进 schema | 与 `getPersonalInfo`/`browser_fill_form` 现有逻辑零改动，无双份维护 |
| 历史数据清理 | `profile_storage.load()` 统一 pop 掉 internship/project | 单一收口点，页面与工具都读不到旧数据 |
| 预设兼容 | 未改动时 schema 默认=现有 10 字段，键名不变 | 旧数据、既有工具调用零迁移（N4） |
| 改名/删除的键行为 | 改名只动 label；删除时键从 schema/值/脱敏列表一并移除 | 保证 LLM 键值映射一致（N5/AC10） |
