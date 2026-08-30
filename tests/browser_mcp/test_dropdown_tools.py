"""browser_mcp.fill_dropdowns.browser_fill_dropdowns 的单测（mock call_tool）。

验证新搬移版函数：按字段名取 ref、value 填写与脱敏展示、展开→匹配→点选。
值由调用方解析真实值后直接传入，敏感字段以 {"display": "***"} 标记展示。
"""

import pytest

from src.browser_mcp.fill_dropdowns import browser_fill_dropdowns


def _snap_with_popup(options: list[str], expanded_ref: str = "e103") -> str:
    """构造全局快照：page（首个顶层块被 find_popup 排除）+ 弹层（可选项行）。"""
    lines = [
        "- generic [ref=page]:",
        "  - generic [ref=body]: 主体内容",
        "- generic [ref=pop]:",
    ]
    for i, text in enumerate(options):
        lines.append(f"  - generic [ref=opt_{i}] [cursor=pointer]: {text}")
    return "\n".join(lines)


class FakeCall:
    """模拟 MCP：点击记录目标；快照按最后一次点击的下拉框返回对应弹层。"""

    def __init__(self, popups: dict[str, list[str]]):
        self.popups = popups
        self.clicks: list[str] = []

    async def __call__(self, name, args=None):
        args = args or {}
        if name == "browser_click":
            self.clicks.append(args.get("target"))
            return "ok", False
        if name == "browser_snapshot":
            last = self.clicks[-1] if self.clicks else "e103"
            return _snap_with_popup(self.popups.get(last, [])), False
        return "?", True


def _install_fake(monkeypatch, fake):
    for path in (
        "src.browser_mcp.client.call_tool",
        "src.browser_mcp.dropdown.call_tool",
    ):
        monkeypatch.setattr(path, fake)
    return fake


@pytest.mark.asyncio
async def test_fill_by_name_clicks_matching_options(monkeypatch):
    fake = _install_fake(monkeypatch, FakeCall({
        "e103": ["合肥", "上海"],        # 面试站点
        "e285": ["安徽省", "北京市"],    # 籍贯
        "e304": ["中国"],               # 国籍
    }))

    res = await browser_fill_dropdowns(
        items=[
            {"name": "面试站点", "value": "合肥"},
            {"name": "籍贯", "value": "安徽省"},
            {"name": "不存在", "value": "x"},                        # 字段名不在 dropdown_fields
            {"name": "国籍", "value": "110101199001011234", "display": "***"},  # 值不在弹层选项中（敏感）
        ],
        dropdown_fields={"面试站点": "e103", "籍贯": "e285", "国籍": "e304"},
    )

    assert not res.is_error
    assert "已填写（2）" in res.output
    assert "[面试站点] → 合肥" in res.output
    assert "[籍贯] → 安徽省" in res.output
    # 字段名不存在 / 选项不匹配 → 未匹配
    assert "未匹配（2）" in res.output
    # 敏感值脱敏：未匹配且不泄露真实值
    assert "***" in res.output
    assert "110101199001011234" not in res.output
    # 点击序列：展开→选中依次为 e103、opt_0、e285、opt_0；不存在 未点击；e304 展开后无匹配
    assert fake.clicks == ["e103", "opt_0", "e285", "opt_0", "e304"]


@pytest.mark.asyncio
async def test_fill_value_empty_is_unmatched(monkeypatch):
    fake = _install_fake(monkeypatch, FakeCall({"e103": ["合肥", "上海"]}))

    res = await browser_fill_dropdowns(
        items=[{"name": "面试站点", "value": ""}],
        dropdown_fields={"面试站点": "e103"},
    )

    assert not res.is_error
    assert "已填写（0）" in res.output
    assert "未匹配（1）" in res.output
    assert "目标值为空" in res.output
    assert fake.clicks == []  # 空值不点击


@pytest.mark.asyncio
async def test_fill_item_without_value_is_unmatched(monkeypatch):
    """item 缺 value（或 value 为 None）→ 目标值为空，不点击。"""
    fake = _install_fake(monkeypatch, FakeCall({"e103": ["合肥", "上海"]}))

    res = await browser_fill_dropdowns(
        items=[{"name": "面试站点", "value": None}],
        dropdown_fields={"面试站点": "e103"},
    )

    assert not res.is_error
    assert "已填写（0）" in res.output
    assert "未匹配（1）" in res.output
    assert "目标值为空" in res.output
    assert fake.clicks == []