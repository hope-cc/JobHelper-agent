# 投递表单下拉框选项探测与填写 Plan

## 架构概览

新增一个共享辅助模块 + 两个工具，改动两处既有文件：

- **`src/browser_mcp/dropdown.py`**（新增）：下拉框的**程序化识别**、快照**子树裁切**、**选项提取**与**展开/收起辅助**。纯函数可单测，异步辅助复用 `call_tool`。
- **`src/tools/builtin/browser_probe_dropdowns.py`**（新增，工具 1）：自动识别全部下拉框候选，对未填者逐个展开探测选项并返回。
- **`src/tools/builtin/browser_fill_dropdowns.py`**（新增，工具 2）：按 {ref, 目标值} 展开、匹配、点击填写。
- **`src/prompt/prompt.py`**（修改）：`SubmitFlow` 补充下拉框识别与填写步骤。
- **`src/tools/builtin/browser_snapshot.py`**（修改）：工具描述补充「下拉框由 browser_probe_dropdowns 自动识别」。

识别完全程序化：两个工具内部调用**原始 MCP `browser_snapshot`**（非本项目的 wrapper，避免 print 噪音），用缩进树解析后按结构规则判断，LLM 只负责填什么值。

## 核心数据结构

### 下拉框候选 Candidate
```python
{"ref": str,        # 触发元素 ref（generic [cursor=pointer]）
 "label": str,      # 同层前序兄弟的字段标签（如「* 籍贯」），无则 ""
 "display": str,    # 当前显示值（未填为「请选择」）
 "is_empty": bool}  # display 含「请选择」或为空
```

### 选项 Option
```python
{"value": str,      # 选项文本
 "ref": str,        # 可点击 ref（listitem 自身或其后代），无则 ""（不可点击）
 "selected": bool}
```

## 模块设计

### src/browser_mcp/dropdown.py

**职责：** 下拉框识别、子树裁切、选项提取、展开/收起。

**接口：**
- `parse_tree(text) -> list[Node]`：把快照文本解析为缩进树（Node 含 indent/content/ref/children）。
- `find_dropdown_candidates(snapshot_text) -> list[Candidate]`：遍历树，命中 `generic` + `[cursor=pointer]` + 存在 `list` 后代 即候选；`display` 取子树内首个 `generic...: <文本>`；`label` 取同层前序兄弟的 `generic...: <文本>`。
- `crop_subtree(snapshot_text, ref) -> str`：定位 `[ref=<ref>]` 行，取该行起至缩进 ≤ 该行前所有行。ref 不存在返回 ""。
- `extract_options(subtree) -> list[Option]`：取子树内 `listitem` 节点（value=子树首个文本，ref=listitem ref 或首个带 ref 后代）；兜底 `option "x" [ref=y]` 行。
- `find_option_ref(options, target) -> (ref, matched_value)`：value 精确优先、其次 target ∈ value。
- `EXPAND_WAIT_SECONDS = 0.6`、`COLLAPSE_WAIT_SECONDS = 0.3`
- `async expand_and_crop(ref) -> (cropped, err)`：`browser_click` 展开 → sleep → 原始 `browser_snapshot` → `crop_subtree`。
- `async collapse(ref) -> (text, err)`：`browser_click` 同一 ref 收起（toggle）→ sleep。

**依赖：** `src.browser_mcp.client.call_tool`

### browser_probe_dropdowns.py

**职责：** 自动识别 + 探测未填下拉框。

**Params：** `refs: list[str] = []`（可选，限定探测范围；空 = 识别全部）

**流程：**
1. 原始 `browser_snapshot` 取快照；失败即返回错误。
2. `find_dropdown_candidates` 得到候选；若传了 refs，只保留命中项（未命中记为「无效 ref」）。
3. 逐候选：已填 → 跳过并列出；未填 → `expand_and_crop` → `extract_options` → `collapse` 收起。展开失败/无选项如实记录。
4. 返回清单报告（ref/标签/当前值/选项数）。

### browser_fill_dropdowns.py

**职责：** 按 {ref, 目标值} 填写下拉框。

**Params：** `items: [{ref, value?, data_key?}]`（data_key 优先，其次字面量 value）

**流程：**
1. 取一次快照 → 候选 ref 集合，**先校验全部 item.ref**（无效/非下拉框记为跳过，**不点击**，避免误触按钮）。
2. 逐有效项：解析目标值（data_key → 后台真实值）→ `expand_and_crop` → `extract_options` → `find_option_ref`。未匹配/选项无 ref 记为未匹配；命中则 `browser_click` 点击选项 ref。
3. 报告已填/未匹配/失败；真实值经 `_scrub` 脱敏后返回（敏感字段显示 ***）。

### 修改

- `src/prompt/prompt.py`：`SubmitFlow` 插入：`browser_probe_dropdowns`（自动识别并探测未填下拉框选项）→ `browser_fill_dropdowns`（[{ref, data_key|value}] 填写下拉框）。
- `src/tools/builtin/browser_snapshot.py`：描述补充一句「下拉框（generic [cursor=pointer]）由 browser_probe_dropdowns 自动识别与探测」。

## 模块交互

```
browser_probe_dropdowns
  └─ call_tool("browser_snapshot")  → find_dropdown_candidates
       └─ 每个未填候选: expand_and_crop → extract_options → collapse
browser_fill_dropdowns
  ├─ call_tool("browser_snapshot")  → 候选 ref 校验
  └─ 每个有效 item: 解析值 → expand_and_crop → find_option_ref → call_tool("browser_click", 选项 ref)
```

## 文件组织

```
docs/MCP投递表单下拉框填写/
  ├── spec.md / plan.md / task.md / checklist.md
src/browser_mcp/dropdown.py
src/tools/builtin/browser_probe_dropdowns.py
src/tools/builtin/browser_fill_dropdowns.py
src/prompt/prompt.py                    （修改）
src/tools/builtin/browser_snapshot.py   （修改）
tests/browser_mcp/test_dropdown.py
scripts/probe_dropdowns.py              （可选冒烟脚本，连真实 MCP）
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 识别规则 | generic[cursor=pointer] + list 后代 | 真实快照实测 24/24、13 非下拉框零误报 |
| 识别阶段 | 纯程序，LLM 不参与 | 用户明确要求 |
| 标签提取 | 同层前序兄弟 generic 文本 | 与真实结构一致（面试站点/籍贯/国籍均成立） |
| 裁切 | 缩进子树切片 | 无第三方依赖，输出小 |
| 选项提取 | listitem 优先，option 兜底 | 覆盖站点形态 |
| 点击选项 | browser_click 用 listitem ref | MCP v0.0.79 仅支持 ref 点击 |
| 探测后收起 | 再次点击同一 ref（toggle） | 防止面板遮挡后续点击/快照 |
| 填写目标值 | data_key 优先、字面量兜底 | 与脱敏体系一致，兼支持非个人信息值 |
| 无效 ref | 点击前统一校验 | 避免误触「提交」等动作按钮 |
