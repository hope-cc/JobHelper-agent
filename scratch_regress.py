# -*- coding: utf-8 -*-
"""回归验证：list 弹层不带 ref 可识别 + 通用弹层行为不回归 + body 不泄漏。"""
import sys

sys.path.insert(0, r"D:\user\Desktop\JobHelper-agent")

from src.browser_mcp.dropdown import (
    _top_generic_blocks,
    _parse_tree,
    find_popup,
    popup_options,
    popup_option_texts,
)

current_snap = open("snapshot_example.txt", encoding="utf-8").read()

print("== 当前快照顶层块 ==")
for i, b in enumerate(_top_generic_blocks(_parse_tree(current_snap))):
    print(f"  [{i}] {b['content'][:60]}")

checks = []

# ---- 用户报告的场景：list 弹层，不带 ref（popup 命令行为） ----
pop = find_popup(current_snap)  # 不带 ref，正是 REPL popup 命令的调用方式
checks.append(("list弹层-不带ref识别", pop is not None and pop.get("ref") == "e1741"))
if pop is not None:
    texts = popup_option_texts(pop)
    checks.append(("list弹层-选项是/否", texts == ["是", "否"]))
    checks.append(("list弹层-无body泄漏", "添加教育经历" not in texts and "姓名" not in texts))

# ---- 带 ref 场景仍正常（expand/probe 调用路径） ----
pop2 = find_popup(current_snap, "e567")
checks.append(("list弹层-带ref识别", pop2 is not None and pop2.get("ref") == "e1741"))

# ---- 无弹层时仍返回 None（body 不泄漏） ----
body_only = current_snap.split("  - list [ref=e1741]:", 1)[0]
checks.append(("无弹层-不带ref->None", find_popup(body_only) is None))
checks.append(("无弹层-带ref->None", find_popup(body_only, "e567") is None))

# ---- 选项文本仍为纯文本 ----
if pop is not None:
    checks.append(("选项为纯文本", all(not t.startswith("generic") and not t.startswith("listitem") for t in popup_option_texts(pop))))

print()
print("\n".join(f"[{'PASS' if ok else 'FAIL'}] {name}" for name, ok in checks))
print("ALL-PASS ✓" if all(ok for _, ok in checks) else "HAS-FAIL ✗")
sys.exit(0 if all(ok for _, ok in checks) else 1)