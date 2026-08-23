# 下拉框探测与填写优化 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/browser_mcp/dropdown.py` | 新增弹层定位/选项提取/弹层按钮辅助（find_popup、popup_options 等）；复用既有 _parse_tree/_strip_lines |
| 修改 | `src/tools/builtin/browser_probe_dropdowns.py` | 逐个展开未填下拉框→全局快照→返回 {ref,label,display,options} |
| 修改 | `src/tools/builtin/browser_fill_dropdowns.py` | 四层自适应填写（L1点选→L2输入+点选→L3输入+回车→L4文本兜底）+ 确定按钮 |
| 修改 | `src/prompt/prompt.py` | SubmitFlow 步骤7/8 文案、_SUBMIT_FLOW_NEXT 提示文本同步 |

验证环境：`D:\coding\Anaconda\envs\agent\python.exe`（导入模块时可用；勿自动安装缺失库）。

## 前置共同事实（来自真实快照 snapshot_example.txt）

- 弹层位于页面根 generic 的**最后一个子级**：`e1 → [e3 页主体, …, e1739 区域弹层]`。
- 弹层选项行 = `generic [ref=…] [cursor=pointer]: 文本`（如 `北京市`）；行内圆点是**无文本**的 `generic [cursor=pointer]`。
- 弹层内干扰项（全国/全部省市/已选地区/清空已选/取消/确定）不参与选项提取。
- 弹层搜索框为 `textbox/searchbox`，弹层「确定/确认」「取消」为 generic/button/link 行。

## T1: dropdown.py — 弹层定位 find_popup

**文件：** `src/browser_mcp/dropdown.py`
**依赖：** 无
**步骤：**
1. 新增正则 `_OPTION_TEXT_RE`：匹配 `generic [ref=x] [cursor=pointer]: 文本`（含无 ref 变体），捕获文本组。
2. 新增 `_option_rows(node) -> list[dict]`：递归收集 node 子树内所有匹配 `_OPTION_TEXT_RE` 的节点 `{text, node, parent}`，text 去引号、去空过滤。
3. 新增 `find_popup(snapshot_text) -> dict|None` 判定步骤：
   - `_parse_tree` 解析后，取根 generic 子节点。
   - 若存在多个平级 generic，取**最后一个**（DOM 末尾渲染）；
   - 若只有一个，递归下沉到其「最后一个 generic 子节点」（多包一层），
   - 直到某层 generic 子节点 ≥2 → 取其中含选项行数 ≥2 且为文档序最后的节点为弹层。
   - 全树找不到 → 返回 None。
4. 新增 `popup_options(popup_node) -> list[dict]`：
   - 对弹层内每个选项行 → `{text, click_ref, text_ref}`；
   - `text_ref` 为该行节点 ref；`click_ref` 优先取该行同层兄弟中「无文本 generic [cursor=pointer]」（圆点）的 ref，无则用 `text_ref`；
   - 去重（text 相同只保留首个）。
5. 新增 `popup_confirm/dismiss/filter` 三个小函数：
   - `popup_filter_ref(popup)` — 弹层内首个 textbox/searchbox ref，无则 ""。
   - `popup_confirm_ref(popup)` — 弹层内最后一个名字含「确定/确定/OK」的 generic/button/link ref，无则 ""。
   - `popup_dismiss_ref(popup)` — 弹层内最后一个名字含「取消/关闭」的 ref，无则 ""。

**验证：** 用快照字符串调 `find_popup`/`popup_options`，能定位 e1739、提取出「北京市」等省级选项且不含「全部省市/取消/已选」等噪声。见 T6 测试脚本。

## T2: dropdown.py — 弹层展开/收起并取全局快照

**文件：** `src/browser_mcp/dropdown.py`
**依赖：** T1
**步骤：**
1. 新增 `_snapshot_global()`：优先 `call_tool("browser_snapshot", {"target": "body"})`；出错则回退 `call_tool("browser_snapshot", {})`，均出错返回 (文本, err)。
2. 新增 `async expand_popup(ref) -> (popup_node | None, err)`：点击 `browser_click(ref)` → `EXPAND_WAIT_SECONDS` 等待 → 全局快照 → `find_popup`。点击出错或未找到弹层时返回错误信息（不抛异常）。
3. 新增 `async collapse_open(ref) -> bool`：再次点击同一 ref 收起（toggle）；失败且已知弹层时尝试点弹层内「取消」兜底。

**验证：** 使用 `python -c` 导入模块无语法错误；快速路径单元断言（弹层存在时返回 e1739、无弹层返回 None）。

## T3: browser_probe_dropdowns 重写

**文件：** `src/tools/builtin/browser_probe_dropdowns.py`
**依赖：** T1,T2
**步骤：**
1. 参数仍为可选 `refs`（为空 → 全部未填候选）。
2. 流程：
   - `browser_snapshot`（desktop）→ `find_dropdown_candidates`（复用）裁决 unfilled。
   - 逐个候选：`expand_popup(ref)` → 若成功且 options → 收集；随后 `collapse_open(ref)`；失败记录原因到 `failed`。
   - 组装输出行：`- [ref] label（未填）：选项1 选项2 …`；已填候选仅列示（`已填（无需处理）`）。
3. Description 更新：说明会逐个展开并回填选项清单、清理。

**验证：** 对 `snapshot_example.txt` 中弹层部分的快照直接喂 `find_popup`+`popup_options` 断言输出；模块可导入 (`python.exe -c "import src.tools.builtin.browser_probe_dropdowns"`)。

## T4: browser_fill_dropdowns 重写

**文件：** `src/tools/builtin/browser_fill_dropdowns.py`
**依赖：** T1,T2
**步骤：**
1. 保留 `DropdownFill`（ref/data_key/value）与 `Params`。
2. 主循环对每个 item（先校验 ref 合法 → 目标值解析 + 脱敏）：
   - **L1** `expand_popup` → `popup_options` 匹配目标值（先精确后包含，区分大小写）→ `click_ref`；存在 `popup_confirm_ref` 则再点击确认；
   - **L2** 若弹层含 filter 框：对 `popup_filter_ref` 输入目标值 → 等待 → 重新全局快照 → 再匹配 → 点击选项 + 确认；
   - **L3** 若上述仍无命中且弹层含 filter 框：输入后**按回车**（优先 `browser_press_key`，若无则 JS `page.keyboard.press('Enter')`）→ 等待 → 快照匹配 → 点击 + 确认；
   - **L4** 兜底：`select_by_text(value)`（browser_find/JS）。
   - 任一路径成功 `filled`；全部失败 `unmatched`（带允许文本）。
3. 保留/适配原有 `js 兜底`click_option_by_js；`_confirm_select` 改为弹层已知时用 `popup_confirm_ref`。
4. 报告格式保持已填/未匹配/失败/跳过，敏感值 `***`。
5. Description 更新（含 L1…L4 行为、字母 case）。

**验证：** 模块可导入；纯逻辑「选项文本匹配 + 弹层按钮定位」用快照样例断言。

## T5: prompt.py 流程提示与下一步提醒

**文件：** `src/prompt/prompt.py`
**依赖：** 无（可与 T3/T4 并行）
**步骤：**
1. `SubmitFlow` 步骤7：更新为「调用 browser_probe_dropdowns（无需传参）：工具会逐个展开未填写的下拉框，返回每个下拉框的 ref、标签和可用选项清单」。
2. 步骤8：更新为「根据步骤7的标签与选项清单，结合个人信息决定每个下拉框应选的值，调用 browser_fill_dropdowns 传入 [{ref, data_key 或 value}]」。文案保持敏感信息不入对话。
3. `_SUBMIT_FLOW_NEXT` 中 `browser_probe_dropdowns` → 下一步引导填写；`browser_fill_dropdowns` → 完成汇报。

**验证：** `python3 -c` 可导入；文件中不再出现旧版「仅返回未填写下拉框清单」字样。

## T6: 单元自测（纯解析，不依赖真实浏览器）

**文件：** 临时脚本 `scripts/adhoc_dropdown_check.py`（不入库，验证后删除；或放 test 目录一套）
**依赖：** T1
**步骤：**
1. 从 `snapshot_example.txt` 提取弹层部分（628..741 行）构造样例字符串。
2. 断言 `find_popup` 返回 `e1739`；`popup_options` 提取选项包含「北京市」「安徽省」且不包含「全国、全部省市、已选地区、清空已选、取消、确定」。
3. 断言 `popup_filter_ref` 为 `e1745`、`popup_confirm_ref` 为 `e2120`、`popup_dismiss_ref` 为 `e2116`。

**验证：** 脚本运行全部断言通过后删除。

## 执行顺序

```
T1 → T2 → T3  →  T4
        ↘ T5（可并行，与 T3/T4 无关）→ T6（依赖 T1 即可先跑）
完成后统一过 py_compile + 库内检查
```