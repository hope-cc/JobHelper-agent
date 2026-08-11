# 个人信息字段脱敏 Plan

## 架构概览

三端改动，方向一致：**脱敏配置 = 基本信息字段键的字符串数组**。

1. **前端**：`BasicInfoSection` 在每个字段标签旁渲染「脱敏」checkbox；勾选状态进入 `ProfileContext`（新增 `masked_basic_fields: string[]`）；保存 / 回填时随整份字典走现有 `PUT/GET /api/personal` 链路。
2. **后端**：脱敏配置作为 `profile.json` 顶层保留键 `masked_basic_fields` 持久化（与个人信息同文件、同一份字典），`empty_profile()` 与请求模型补齐该键。
3. **工具**：`getPersonalInfo` 读取 `profile.json`，弹出 `masked_basic_fields`，对 `basic_info` 中「被勾选且值非空」的字段替换为 `"***"`，返回整份 JSON。持久化文件原值不变。

关键取舍：脱敏**只作用于 `basic_info`**，不扫经历类条目。这既匹配用户确认的范围，也规避了 `name` 键歧义（`basic_info.name`=姓名 与 `project[].name`=项目名称 同名，若全局按键扫描会误伤）。

## 核心数据结构

### 脱敏配置

基本信息字段键的字符串数组，如：

```json
"masked_basic_fields": ["phone", "id_number"]
```

- 值为空数组 = 不脱敏任何字段（默认）
- 是 `profile.json` 的顶层保留键，与 7 个档案键并列

### 前端类型（types.ts）

```ts
interface PersonalProfile {
  basic_info: BasicInfo;
  education: EducationEntry[];
  internship: InternshipEntry[];
  project: ProjectEntry[];
  award: AwardEntry[];
  language: LanguageEntry[];
  self_evaluation: string;
  masked_basic_fields: string[];   // 新增：已勾选脱敏的基本信息字段键
}

type SavableProfile = {
  basic_info: BasicInfo;
  education: Omit<EducationEntry, "id">[];
  internship: Omit<InternshipEntry, "id">[];
  project: Omit<ProjectEntry, "id">[];
  award: Omit<AwardEntry, "id">[];
  language: Omit<LanguageEntry, "id">[];
  self_evaluation: string;
  masked_basic_fields: string[];   // 新增
};
```

### 后端（profile_routes.py）

```py
class PersonalProfileBody(BaseModel):
    basic_info: dict
    education: list
    internship: list
    project: list
    award: list
    language: list
    self_evaluation: str
    masked_basic_fields: list[str] = []   # 新增，缺省为空
```

## 模块设计

### 后端 profile_storage.py
**职责：** 不变，仍为 `data/personal/profile.json` 的整份字典读写。
**改动：** `empty_profile()` 顶层增加 `"masked_basic_fields": []`，保证未保存时 GET 也返回一致结构。
**依赖：** 无（标准库）。

### 后端 profile_routes.py
**职责：** 不变，`GET/PUT /api/personal` 透传整份字典。
**改动：** `PersonalProfileBody` 增加可选 `masked_basic_fields`，保存时落盘。
**依赖：** `profile_storage`。

### 工具 src/tools/builtin/get_personal_info.py
**职责：** LLM 可调用的个人信息读取工具，读取时对敏感字段做视图级脱敏。
**对外接口：** `getPersonalInfo`（工具名），无参。
**改动：** 重写现有坏桩文件。
**实现要点：**
1. 空参数模型 `class Params(BaseModel): pass`——满足 `@tool` 装饰器「首个参数为 BaseModel 子类」的约定，JSON Schema 为无必填属性的空对象，LLM 以 `{}` 调用
2. `profile_storage.load()` 读档；文件不存在返回友好提示（N4）
3. `data.pop("masked_basic_fields", [])` 取出配置（同时从输出中剥离元数据）
4. 遍历配置，`basic_info[key]` 值非空时置 `"***"`
5. `json.dumps(data, ensure_ascii=False, indent=2)` 返回
**依赖：** `src.api.profile_storage`（无环：该模块仅依赖标准库）。

### 前端 ProfileContext.tsx
**职责：** 表单状态 reducer。
**改动：** 新增 action `TOGGLE_MASKED_FIELD { key, checked }`；reducer 据此增删 `masked_basic_fields` 集合。
**依赖：** `types.ts`。

### 前端 profileFieldConfigs.ts
**改动：** `emptyProfile()` 增加 `masked_basic_fields: []`。字段配置数组本身不变（脱敏对所有 `BASIC_INFO_FIELDS` 字段生效）。

### 前端 profile/BasicInfoSection.tsx
**职责：** 基本信息分区表单。
**改动：** 每个字段标签行右侧渲染「脱敏」checkbox（勾选 dispatch `TOGGLE_MASKED_FIELD`）；外层元素由 `<label>` 改为 `<div>`，避免嵌套 label 的非法 HTML。
**依赖：** `ProfileContext`、`profileFieldConfigs`。

### 前端 ProfilePage.tsx
**职责：** 页面入口，加载 / 保存 / 回填。
**改动：** `toStateProfile` 读 `saved.masked_basic_fields ?? []`；`toSavableProfile` 输出 `state.masked_basic_fields`。
**依赖：** `ProfileContext`、`profileClient`。

## 模块交互

```
用户勾选「脱敏」→ BasicInfoSection dispatch TOGGLE_MASKED_FIELD → Context.masked_basic_fields 更新
点「保存」→ toSavableProfile（含 masked_basic_fields）→ PUT /api/personal
         → profile_routes 模型校验 → profile_storage.save → profile.json 顶层写入 masked_basic_fields
重新进入页面 → GET /api/personal → toStateProfile 回填 masked_basic_fields → 勾选状态恢复
agent 调用 getPersonalInfo → 读 profile.json → pop masked_basic_fields → basic_info 命中字段置 "***" → 返回脱敏 JSON
```

## 文件组织

```
docs/个人信息管理-字段脱敏/              — 本期四份文档
data/personal/profile.json               — 运行后顶层含 masked_basic_fields
src/api/
├── profile_storage.py                   — 修改：empty_profile 加键
└── profile_routes.py                    — 修改：PersonalProfileBody 加可选键
src/tools/builtin/get_personal_info.py   — 修改：重写实现脱敏读取
frontend/src/
├── types.ts                             — 修改：PersonalProfile / SavableProfile 加 masked_basic_fields
└── components/
    ├── ProfileContext.tsx               — 修改：TOGGLE_MASKED_FIELD action
    ├── ProfilePage.tsx                  — 修改：加载/保存处理 mask
    └── profile/
        ├── profileFieldConfigs.ts       — 修改：emptyProfile 加空数组
        └── BasicInfoSection.tsx         — 修改：字段旁加脱敏 checkbox
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 脱敏配置存储 | profile.json 顶层保留键 `masked_basic_fields` | 单一事实源，复用现有整份字典 GET/PUT 链路，工具一次读取即得配置；旧文件缺键时默认空 |
| 无参工具实现 | 空 Pydantic 模型 `class Params(BaseModel): pass` | 满足 `@tool` 约定，无需改装饰器；Schema 为无必填属性空对象，LLM 以 `{}` 调用 |
| 脱敏范围 | 仅作用于 `basic_info` | 用户已确认；规避 `name` 键与 `project[].name` 的键名歧义 |
| 空值处理 | 仅替换非空值 | 避免把空字符串变 `"***"` 产生假数据，误导 LLM |
| 工具输出 | 剥离 `masked_basic_fields` 元数据后返回整份 JSON | agent 只需知道「哪些字段被脱敏了」，不需要知道脱敏配置本身 |
| 勾选 UI | 字段标签行内嵌 checkbox，外层 label 改 div | 避免嵌套 label 非法 HTML |
