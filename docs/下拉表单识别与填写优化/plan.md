# 下拉框探测与填写优化 Plan

## 架构概览

在既有 `src/browser_mcp/dropdown.py` + 两个 @tool 工具的基础上**增量改造**，不新增模块、不改浏览器客户端/生命周期。

核心是引入「**弹层（popup）程序模型**」：

1. **弹层定位**：展开下拉框后取全局快照，按缩进把根节点下「第二个最高层级的 generic 子树」识别为弹层（对应真实站点的 body 底部 Portal，如 `e1 → [e3 页面主体, e1739 弹层]`）。
2. **选项提取**：从弹层节点解析出选项。探测（probe）只返回**纯文本**；填写（fill）内部额外保留可点击 ref。
3. **交互自适应**：fill 按「点选 → 输入+过滤点选 → 输入+回车 → 文本兜底」顺序尝试多种站点形态。

改造范围：
- `src/browser_mcp/dropdown.py` — 新增弹层定位/选项解析/确定按钮/收起辅助，保留既有识别函数
- `src/tools/builtin/browser_probe_dropdowns.py` — 逐个展开未填下拉框 → 全局快照 → 提取纯文本选项返回
- `src/tools/builtin/browser_fill_dropdowns.py` — 多层自适应填写
- `src/prompt/prompt.py` — SubmitFlow 步骤 7/8 文案与下一步提醒同步更新

## 核心数据结构

```python
# probe 返回的每个下拉框条目
{"ref": str, "label": str, "display": str, "options": list[str], "failed": str}
# display: 当前显示值（未填时为 "" 或占位词）；options: 纯文本选项，去空去重；
# failed: 提取失败原因，成功时 ""；已填下拉框不展开，仅列在汇总行。

# fill 内部解析出的单个选项（供点击）
{"text": str, "click_ref": str, "text_ref": str}
# click_ref: 优先「圆点」（前置选中框）ref，其次「文字」ref；text_ref: 文字节点 ref

# fill 输入
class DropdownFill(BaseModel):
    ref: str      # 下拉框 ref（来自 probe 返回）
    data_key: str  # 个人信息键，优先于 value
    value: str     # 字面量目标值
```

## 模块设计

### 模块 A：弹层定位与解析（dropdown.py 新增）

职责：把「全局快照」变成「可用选项（含可点击 ref）」。

```python
async def expand_popup(ref: str) -> tuple[str, str]:
    """点击 ref 展开下拉框 → 等待 → 全局快照 → 返回 (弹层文本, 错误)。"""
    # browser_click(ref) → sleep(EXPAND_WAIT_SECONDS)
    # browser_snapshot({"target": "body"}) → 提取弹层子树文本

def find_popup(snapshot_text: str) -> dict | None:
    """定位根节点下第二个最高层级 generic 子树（跳过首个外显层/主页面）。"""
    root = _parse_tree(snapshot_text)
    tops = [t for t in root["children"] if t["content"].startswith("generic")]
    if len(tops) >= 2:
        return tops[1]                      # 主规则：第二个顶层 generic
    # 兜底：候选层级中第一个含选项特征（cursor+文本 或 listitem）的节点
    for t in tops:
        if _subtree_has_option_marker(t):
            return t
    return None

def popup_option_texts(popup: dict) -> list[str]:
    """从弹层提取纯文本选项，优先 capture `generic [cursor=pointer]: 文本`，去空去重。

    该特征天然排除弹层 UI 噪声（全国/省市筛选、清空、取消 / 确定 等均无 cursor）。
    """
def popup_options(popup: dict) -> list[dict]:
    """解析每个选项：text / click_ref（选中框 ref，若不外） / text_ref。"""
    # 模式判定：
    #   模式一（组）：generic 节点下含「cursor 无文本（圆点）」+「cursor+文本」两节点
    #   模式二（叶子）：generic 节点自身就是 `[cursor=pointer]: 文本`
    # 二者均以 cursor:pointer 为正选项锚点，排除无 cursor 的占位/筛选行
def popup_filter_ref(popup: dict) -> str:
    """弹层内过滤/搜索输入框 ref（textbox/searchbox），无则 ""。"""
def popup_confirm_ref(popup: dict) -> str:
    """弹层内「确定/确认」元素 ref（generic / button / link），无则 ""。"""
def popup_dismiss_ref(popup: dict) -> str:
    """弹层内「取消」元素 ref，用于收起兜底（防止叠加弹层）。"""
async def collapse(ref: str, snapshot_text: str = "") -> tuple[str, bool]:
    """再次点击同一 ref 收起；失败时尝试弹层「取消」兜底。返回 (内容, is_error)。"""
```

复用既有函数：`find_dropdown_candidates`（识别）、`_parse_tree`、`find_filter_input`（现改为适配弹层）、`find_confirm_button_ref`（弹层内匹配为兜底）、`select_by_text`、`_strip_quotes` 等。

### 模块 B：browser_probe_dropdowns 改造

```python
@tool(name="browser_probe_dropdowns", description=...)
async def browser_probe_dropdowns(params: Params):   # Params 保留可选 refs（为空则全部未填）
    snap, err = await call_tool("browser_snapshot", {"target": "body"})
    candidates = find_dropdown_candidates(snap)      # 识别（既有逻辑）
    unfilled = [c for c in candidates if c["is_empty"]]
    results = []
    for c in unfilled:
        pop, perr = await expand_popup(c["ref"])          # 展开 → 全局快照 → 弹层
        if perr:
            results.append({**c, "options": [], "failed": perr})
            await collapse_popup(c["ref"], "")
            continue
        opts = popup_option_texts(pop)
        await collapse_popup(c["ref"], pop)
        results.append({**c, "options": opts, "failed": ""})
    return ToolResult(output=_format_probe_report(candidates, results))
```

- **展开 → 快照 → 收起 → 下一个**，逐个推进，绝不多个弹层并存。
- 已填下拉框不展开，仅出现在汇总行（含当前值）。
- 返回文本格式：
  ```
  下拉框探测结果（未填 N 个）：
  - [ref] 字段label（未填）：选项 → 北京/天津/上海/…
  已填（无需处理）：[ref] 字段label：当前值
  未识别弹层：[ref]：原因
  ```

### 模块 C：browser_fill_dropdowns 改造

```text
@tool(name="browser_fill_dropdowns", ...)
async def browser_fill_dropdowns(params: Params):
    初始化 profile；快照 → 候选校验（invalid ref 跳过）
    for item in params.items:
        value/display 解析（data_key 优先，敏感脱敏）
        └─ 多层改编尝试：
        L1 直接弹层点选
            pop = expand_popup(item.ref)
            match = popup_options(pop) 匹配目标值（精确→包含）
            命中 → click (click_ref) → （若弹层含「确定/确认」则连点）→ filled
        L2 输入 + 过滤点选
            弹层含过滤输入 → browser_type(value) → wait → 全局快照 → 新弹层
            → 匹配 → click click_ref → 确定
        L3 输入 + 回车
            browser_type(value)（在过滤框）→ browser_press_key Enter = 兜底 JS →
            若有确定按钮则点
        L4 文本兜底
            select_by_text(value)（browser_find / JS）
        全部仍未选到 → unmatched（记录原因）
    返回 已填 / 未匹配 / 失败 / 跳过 报告（敏感脱敏为 ***）
```

交互序列（真实站点 zhiye 意向工作地点，通用走 probe→fill）：

```
probe:
  click e139(下拉框) → snapshot → 弹层 e1739 → 纯文本 [北京市…] → collapse
fill:
  LLM 判断"北京" 或 依据 label→data_key → fill item
  click e139 → snapshot → 弹层 → 无匹配 → 有过滤框 → type 北京 → 重快照
  → click 目标选项 → click 弹层「确定」 → filled
```

## 模块交互

```
LLM/流程                    probe/fill 工具                 dropdown.py         MCP
   │                            │                            │                  │
 步骤7: browser_probe_dropdowns │                            │                  │
   │ ── 无参 ──>            │ ── click→snap→extract─collapse →│                  │
   │ <── ref/label/options ─  │ ◄─────────────────────────                    │
 步骤8: browser_fill_dropdowns
   │ ── items[{ref,data_key|value}] ──>  │                    │                  │
   │                          │ L1/L2/L3/L4 依次尝试 → 报告  │                  │
   │ ◄────────────── 填写报告 ───────────────│                                    │
```

## 文件组织

```
src/browser_mcp/dropdown.py                  # 修改 — 新增弹层定位/解析/确定/收起
src/tools/builtin/browser_probe_dropdowns.py # 修改 — 逐个展开取样并返回选项
src/tools/builtin/browser_fill_dropdowns.py  # 修改 — 多层自适应填写
src/prompt/prompt.py                         # 修改 — 步骤7/8文案 & 下一步提示
docs/下拉表单识别与填写优化/spec.md           # 已批准
                        /plan.md              # 本文件
                        /task.md              # 下一阶段生成
                        /checklist.md         # 下一阶段生成
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 弹层定位 | 全局快照中「根下第二个顶层 generic」；兜底扫描含选项标记的顶层节点 | 与用户约定及真实站点（e1→[主主体,弹层]）一致；多站兼容 ≥2 顶层形态 |
| 选项提取规则 | `generic [cursor=pointer]: 文本` 为锚，辅以「圆点(cursor)+文本」组合解析 | 真实快照中该特征天然排除「全国/省市筛选/取消/确定」等无 cursor 噪声 |
| 探测点击作用域 | 仅未填下拉框逐个展开；已填不展开、仅汇总 | 用户已确认；避免多余点击打扰已填状态 |
| 探测返回 | probe 只返回纯文本选项；可点击 ref 在 fill 阶段重取 | 精简 LLM 上下文，选项攻击面小 |
| 填写优先级 | L1 点选 → L2 输入+点 → L3 输入+回车 → L4 文本兜底 | 覆盖真实形态，直点最快且最不易误动 |
| 点击目标 | 优先「圆点」（无文本 cursor 节点），其次文本节点 | 圆点点击最符合选中语义；多站点同构 |
| 判定成功 | 「动作成功即算」（点击/回车无报错即记 filled） | 用户已确认；不回读显示值 |
| 确定按钮 | 只在弹层内匹配「确定/确认」（最后出现）点击 | 避免误点表单级「提交/保存」 |
| 关闭兜底 | 收起失败 → 点弹层「取消」；确保无残留弹层 | 防止 next 动作被遮挡 |
| 回车 | 优先 MCP 键盘事件 / 回退 JS | 兼容 MCP 版本差异 |
| 兼容 | find_popup 找不到弹层（原生 select 或其它结构）→ 回退既有 `expand_and_crop` 路径 | 延续既有对原生下拉的支持 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 站点弹层非「第二顶层 generic」（多 portal 叠加或新结构） | find_popup 按「含选项标记的顶层节点」兜底 + 回退既有路径 |
| 过滤等待不足，快照取到旧弹层 | 复用既有 EXPAND/FILTER 等待时长，必要时重建全局快照 |
| 「确定」点击动作成功但值未真正落位 | 动作成功即计——用户已知可能存在虚报；未命中时 L2/L3 可重试新快照 |
| probe 展开后误点页面其它链接 | 只点击已校验的候选 ref，逐个顺序执行，失败即拆、不并行 |