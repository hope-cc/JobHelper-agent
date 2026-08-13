# 投递表单下拉框选项探测与填写 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/browser_mcp/dropdown.py` | 识别/裁切/选项提取/展开收起辅助 |
| 新建 | `src/tools/builtin/browser_probe_dropdowns.py` | 工具1：自动识别+探测选项 |
| 新建 | `src/tools/builtin/browser_fill_dropdowns.py` | 工具2：按目标值填写 |
| 修改 | `src/prompt/prompt.py` | SubmitFlow 补下拉框流程 |
| 修改 | `src/tools/builtin/browser_snapshot.py` | 描述补下拉框提示 |
| 新建 | `tests/browser_mcp/test_dropdown.py` | 纯函数单测 |
| 新建 | `scripts/probe_dropdowns.py` | 真实 MCP 冒烟（可选） |

## T1: dropdown.py 辅助模块

**文件：** `src/browser_mcp/dropdown.py`
**依赖：** 无
**步骤：**
1. 实现 `parse_tree`（缩进栈解析，Node 含 indent/content/ref/children）。
2. 实现 `find_dropdown_candidates`（generic + cursor=pointer + list 后代；提取 label/display/is_empty）。
3. 实现 `crop_subtree`（按缩进切片）与 `extract_options`（listitem 优先、option 兜底）。
4. 实现 `find_option_ref`（精确→包含）。
5. 实现 `expand_and_crop`、`collapse` 异步辅助与等待常量。

**验证：** `D:/coding/Anaconda/envs/agent/python.exe -c "import src.browser_mcp.dropdown"` 无错。

## T2: dropdown 纯函数单测

**文件：** `tests/browser_mcp/test_dropdown.py`
**依赖：** T1
**步骤：**
1. 用真实快照片断（含未填/已填下拉框、上传按钮、「至今」切换钮）构造用例。
2. 断言识别结果（数量、ref、label、is_empty）、裁切、选项提取、find_option_ref。

**验证：** `pytest tests/browser_mcp/test_dropdown.py` 全过。

## T3: browser_probe_dropdowns 工具

**文件：** `src/tools/builtin/browser_probe_dropdowns.py`
**依赖：** T1
**步骤：**
1. 定义 Params（refs 可选）。
2. 实现自动识别 → 逐未填候选探测 → 收起 → 报告。

**验证：** 单测断言报告含候选清单与选项（mock call_tool）。

## T4: browser_fill_dropdowns 工具

**文件：** `src/tools/builtin/browser_fill_dropdowns.py`
**依赖：** T1
**步骤：**
1. 定义 Params（items: {ref, value?, data_key?}）。
2. 实现快照校验 ref → 解析值 → 展开匹配 → 点击 → 脱敏报告。

**验证：** 单测断言已填/未匹配/失败分类与脱敏。

## T5: 集成修改

**文件：** `src/prompt/prompt.py`、`src/tools/builtin/browser_snapshot.py`
**依赖：** 无
**步骤：**
1. SubmitFlow 插入 probe/fill 步骤。
2. browser_snapshot 描述补下拉框提示。

**验证：** 重启后端，聊天中 browser_snapshot 与流程提示可见（人工）。

## T6: 全量测试与冒烟

**文件：** 全部
**依赖：** T2-T5
**步骤：**
1. `pytest tests` 全量通过。
2. （可选）`scripts/probe_dropdowns.py` 连真实 MCP 探测当前表单。

**验证：** 既有测试全过；冒烟输出候选与选项。

## 执行顺序

```
T1 → T2 ──→ T3 ──→ T5 ──→ T6
          └──→ T4 ──→
```
