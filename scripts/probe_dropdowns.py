"""下拉框识别冒烟脚本。

用法：
  python scripts/probe_dropdowns.py --file <快照文本文件>   # 离线：对本地快照做识别
  python scripts/probe_dropdowns.py                          # 在线：连真实 MCP 识别当前页面

在线模式需先启动 Playwright MCP（且未被其他会话占用浏览器）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser_mcp.dropdown import find_dropdown_candidates


def _dump(cands: list[dict]) -> None:
    print(f"识别到 {len(cands)} 个下拉框候选：")
    for c in cands:
        state = "未填" if c["is_empty"] else f"已填({c['display']})"
        print(f"  [{c['ref']}] {c['label'] or '(无标签)'}：{state}")


def offline(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    _dump(find_dropdown_candidates(text))
    return 0


async def online() -> int:
    from src.browser_mcp.client import call_tool

    snap, err = await call_tool("browser_snapshot", {})
    if err:
        print(f"快照失败：{snap}")
        return 1
    _dump(find_dropdown_candidates(snap))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="下拉框识别冒烟脚本")
    ap.add_argument("--file", help="离线模式：读取本地快照文本文件")
    args = ap.parse_args()
    if args.file:
        return offline(args.file)
    return asyncio.run(online())


if __name__ == "__main__":
    sys.exit(main())
