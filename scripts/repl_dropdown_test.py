# -*- coding: utf-8 -*-
"""下拉框探测与弹层选项提取 · 交互式调试脚本。

复现并观察 browser_probe_dropdowns / browser_fill_dropdowns 的「分割」过程：
先把全局快照切成「下拉框候选」分块，再把弹层切成「选项」分块，分步打印到终端。

前置：已用 Playwright MCP 服务打开目标页（有头）：
    npx @playwright/mcp --port 8931 --user-data-dir <你的浏览器profile目录>

用法：
    D:/coding/Anaconda/envs/agent/python.exe repl_dropdown_test.py

交互命令：
  输入命令或直接按 Enter 重跑上一次分析（默认首次为 inspect）
  navigate <url> / open <url>   在该 session 浏览器里新开页面导航
  inspect                       一键：顶层块分割 + 下拉框候选 + 弹层与选项分割
  snapshot / snap               只打印全局快照检查点（顶层分割 + 候选列表）
  dropdowns / dd/  dlist         只打印下拉框候选（ref/标签/是否未填）
  popup                         手动点开下拉框后，从当前快照定位弹层并列选项
  expand <ref>                  程序化点某下拉框，打印弹层并列出选项（不收起）
  collapse                      收起弹层（依次：再点原 ref → 点取消 → Escape）
  probe                         遍历所有未填下拉框：展开→打印选项→收起
  dump                          当前全局快照与弹层子树存到 dump_snapshot.txt
  help / h                       打印帮助
  quit / exit / Ctrl-C          退出
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.browser_mcp import client
from src.browser_mcp.dropdown import (
    _option_rows,
    _parse_tree,
    _subtree_has_search_box,
    _top_generic_blocks,
    close_popup,
    expand_popup,
    find_dropdown_candidates,
    find_popup,
    popup_confirm_ref,
    popup_dismiss_ref,
    popup_filter_ref,
    popup_options,
    popup_option_texts,
)

HELP = r"""
───────────────── 下拉调试 REPL ─────────────────
  navigate <url>         打开/导航到投递页（有头）
  inspect                一键：顶层块分割 + 候选 + 弹层选项分割（Enter 键=重跑）
  snapshot / snap        打印全局快照分割 + 候选下拉框
  dropdowns / dd          仅打印候选下拉框（ref/标签/是否未填）
  popup                   手动点了下拉框后 → 解析弹层并列出「选项分割结果」
  expand <ref>            程序化点某下拉框 → 打印弹层（不收起）
  collapse                收起弹层（再点原ref / 点取消 / Escape 兜底）
  probe                   遍历所有未填下拉框：展开→列选项→收起
  dump                    写当前快照 + 弹层子树到 dump_snapshot.txt
  help / quit / Ctrl-C    帮助 / 退出
────────────────────────────────────────────────
"""


# ---------- 打印辅助 ----------

def _subtree_lines(node) -> list[str]:
    out: list[str] = []
    def walk(n, d):
        out.append("  " * d + "- " + n["content"])
        for c in n["children"]:
            walk(c, d + 1)
    walk(node, 0)
    return out


def print_top_blocks(snapshot_text: str) -> None:
    root = _parse_tree(snapshot_text)
    blocks = _top_generic_blocks(root)
    print("◆ 顶层块分割（决定弹层归属）")
    if not blocks:
        print("   （无顶层 generic 块）")
        return
    for i, b in enumerate(blocks):
        rows = _option_rows(b)
        has_search = _subtree_has_search_box(b)
        print(
            f"  [{i}] ref={b['ref']!r}  可选行={len(rows)}  搜索框={has_search}"
            f"  首行={b['content'][:44]!r}"
        )


def print_candidates(snapshot_text: str) -> None:
    cands = find_dropdown_candidates(snapshot_text)
    print(f"◆ 下拉框候选（共 {len(cands)}）")
    if not cands:
        print("   （未识别到下拉框）")
        return
    for c in cands:
        state = "未填" if c["is_empty"] else "已填"
        print(f"  [{c['ref']}] {c['label'] or '(无标签)'}  {state}  display={c['display']!r}")
    return cands


def print_popup_node(pop, show_tree: bool = True) -> None:
    if pop is None:
        print("◇ 弹层：未找到")
        return
    opts = popup_options(pop)
    texts = popup_option_texts(pop)
    print(f" 弹层 ref={pop['ref']!r}  首行={pop['content'][:44]!r}")
    print(f"  ▶ 选项分割结果（{len(texts)} 项）：")
    if texts:
        print("    " + " / ".join(texts))
    else:
        print("    （空）")
    print(f"  ▶ 可点击条目（{len(opts)} 条）：")
    for o in opts[:12]:
        print(f"    text={o['text']!r}  ref={o['ref'] or '∅'}  circle={o['circle_ref'] or '∅'}")
    if len(opts) > 12:
        print(f"    … 共 {len(opts)} 条")
    filt = popup_filter_ref(pop)
    conf = popup_confirm_ref(pop)
    dis = popup_dismiss_ref(pop)
    print(f"  ▶ 弹层辅助 ref：filter={filt or '∅'}  confirm={conf or '∅'}  dismiss={dis or '∅'}")
    if show_tree:
        lines = _subtree_lines(pop)
        print(f"  ▶ 弹层子树（{len(lines)} 行，前 40 / 末 12）")
        for l in lines[:40]:
            print("    " + l)
        if len(lines) > 52:
            print("    … 中间省略 …")
            for l in lines[-12:]:
                print("    " + l)
        elif len(lines) > 40:
            for l in lines[40:]:
                print("    " + l)


async def inspect_once() -> None:
    snap, err = await client.call_tool("browser_snapshot", {"target": "body"})
    if err:
        print(f"◇ snapshot 失败：{snap}")
        return
    print_top_blocks(snap)
    print()
    print_candidates(snap)
    print()
    pop = find_popup(snap)
    print_popup_node(pop if pop else None)


# ---------- 主 REPL ----------

async def main() -> None:
    print(HELP)
    last_expanded = ""
    last_action = "inspect"

    while True:
        try:
            raw = (await asyncio.to_thread(input, "\ncmd> ")).strip()
        except (EOFError, KeyboardInterrupt, asyncio.CancelledError):
            print("\n退出。")
            break
        if not raw:
            raw = last_action
        last_action = raw
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        try:
            if cmd in ("help", "h", "?"):
                print(HELP)

            elif cmd in ("navigate", "open", "nav", "go", "goto"):
                if not arg:
                    print("  用法: navigate <url>")
                    continue
                text, err = await client.call_tool("browser_navigate", {"url": arg})
                print("navigate:", ("ERR: " if err else "OK  ") + (text[:400] if text else ""))

            elif cmd in ("snapshot", "snap"):
                insp, err = await client.call_tool("browser_snapshot", {"target": "body"})
                if err:
                    print("snapshot 失败：", insp)
                    continue
                print(insp)
                # print_top_blocks(insp)
                # print()
                # print_candidates(insp)

            elif cmd in ("dropdowns", "dropdown", "dd"):
                insp, err = await client.call_tool("browser_snapshot", {"target": "body"})
                if err:
                    print("snapshot 失败：", insp)
                    continue
                print_candidates(insp)

            elif cmd in ("popup", "pop"):
                insp, err = await client.call_tool("browser_snapshot", {"target": "body"})
                if err:
                    print("snapshot 失败：", insp)
                    continue
                pop = find_popup(insp)
                print_popup_node(pop)

            elif cmd == "expand":
                if not arg:
                    print("  用法: expand <ref>")
                    continue
                ref = arg.strip()
                popup, errmsg = await expand_popup(ref)
                if errmsg:
                    print(f"expand 失败：{errmsg}")
                else:
                    print_popup_node(popup)
                    last_expanded = ref

            elif cmd == "collapse":
                if not last_expanded:
                    print("  还没有展开过下拉框（先用 expand <ref> 或手动点开）")
                    continue
                text, err = await close_popup(last_expanded)
                print("collapse:", ("ERR: " if err else "OK   ") + text[:120])
                last_expanded = ""

            elif cmd in ("probe", "probe-all"):
                insp, err = await client.call_tool("browser_snapshot", {"target": "body"})
                if err:
                    print("snapshot 失败：", insp)
                    continue
                cands = find_dropdown_candidates(insp)
                unfilled = [c for c in cands if c["is_empty"]]
                print(f"◆ probe：未填下拉框 {len(unfilled)} 个，逐个展开取选项")
                for c in unfilled:
                    print(f"\n── [{c['ref']}] {c['label'] or '(无标签)'} ──")
                    pop, e = await expand_popup(c["ref"])
                    if e:
                        print("  expand 失败：", e)
                        continue
                    print_popup_node(pop, show_tree=False)
                    await close_popup(c["ref"])
                print("\nprobe 完（所有弹层已收起）")

            elif cmd == "dump":
                insp, err = await client.call_tool("browser_snapshot", {"target": "body"})
                if err:
                    print("snapshot 失败：", insp)
                    continue
                with open("dump_snapshot.txt", "w", encoding="utf-8") as f:
                    f.write("======== 全局快照 ========\n")
                    f.write(insp + "\n")
                    pop = find_popup(insp)
                    if pop:
                        f.write("\n======== 弹层子树 ========\n")
                        f.write("\n".join(_subtree_lines(pop)) + "\n")
                print("已写 dump_snapshot.txt")

            elif cmd in ("inspect", "in"):
                await inspect_once()

            elif cmd in ("quit", "q", "exit", "退出"):
                print("退出。")
                break

            else:
                print(f"未知命令：{cmd}（输入 help 查看命令）")

        except (Exception, BaseExceptionGroup) as exc:
            print(f"命令执行出错：{exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        import asyncio as _a
        try:
            _a.run(client.close())
        except Exception:
            pass