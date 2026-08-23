# -*- coding: utf-8 -*-
"""最终验收：编译 + 导入 + 快照隔离（正反例）+ options 正确性 + prompt 文案。"""
import sys

sys.path.insert(0, r"D:\user\Desktop\JobHelper-agent")

checks = []

# ---- 1. 导入 ----
import importlib
for m in (
    "src.browser_mcp.dropdown",
    "src.browser_mcp.fill",
    "src.tools.builtin.browser_probe_dropdowns",
    "src.tools.builtin.browser_fill_dropdowns",
    "src.prompt.prompt",
):
    importlib.import_module(m)
    checks.append((f"导入 {m.split('.')[-1]}", True))

# ---- 2. 弹层隔离 ----
from src.browser_mcp.dropdown import (
    find_popup,
    popup_option_texts,
    popup_options,
    popup_filter_ref,
    popup_confirm_ref,
    popup_dismiss_ref,
    find_dropdown_candidates,
)

snap = open("snapshot_example.txt", encoding="utf-8").read()
pop = find_popup(snap, "e139")
checks.append(("弹层=e1739", pop is not None and pop["ref"] == "e1739"))

if pop:
    texts = popup_option_texts(pop)
    opts = popup_options(pop)
    checks.append(("32个省选项", len(texts) == 32 and "北京市" in texts and "台湾省" in texts))
    checks.append(("选项为纯文本", all(not t.startswith("generic") and "[ref" not in t for t in texts)))
    checks.append(("无 body/弹层UI噪声", not any(x in texts for x in ("全国", "全部省市", "已选地区", "清空已选", "取消", "确定", "添加教育经历"))))
    checks.append(("圆圈ref", opts[0]["circle_ref"] == "e1758" and opts[0]["ref"] == "e1762"))
    checks.append(("searche", popup_filter_ref(pop) == "e1745"))
    checks.append(("confirm/dismiss", popup_confirm_ref(pop) == "e2120" and popup_dismiss_ref(pop) == "e2116"))

# 反例：无弹层时不得返回 body
body_snap = snap.split("  - generic [ref=e1739]:", 1)[0]
checks.append(("无弹层->None(带ref)", find_popup(body_snap, "139") is None))
checks.append(("无弹层->None(不带ref)", find_popup(body_snap) is None))

# ---- 3. prompt 文案 ----
import src.prompt.prompt as P
s7 = "选项清单" in P.SubmitFlow and "ref" in P.SubmitFlow
checks.append(("prompt 步骤7含选项清单", s7))
checks.append(("prompt 下一步提醒更新", "选项清单" in P.next_step_reminder("browser_probe_dropdowns")))

print("\n".join(f"[{'PASS' if ok else 'FAIL'}] {name}" for name, ok in checks))
failed = [n for n, ok in checks if not ok]
if failed:
    print("FAILED:", failed)
    sys.exit(1)
print("ALL-PASS")