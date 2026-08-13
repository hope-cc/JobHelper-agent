"""browser_probe_dropdowns / browser_fill_dropdowns 两个工具的单测（mock call_tool）。"""

import pytest

from src.tools.builtin.browser_fill_dropdowns import browser_fill_dropdowns
from src.tools.builtin.browser_probe_dropdowns import browser_probe_dropdowns

# 探测用快照：e103 / e285 未填、e304 已填；均带字段标签
COLLAPSED = """\
- generic [ref=sec1]:
  - generic [ref=l103]: 面试站点
  - generic [ref=e103] [cursor=pointer]:
    - generic [ref=e105]: 请选择
    - list [ref=e106]:
      - listitem [ref=e107]:
        - textbox [ref=e108]
- generic [ref=sec2]:
  - generic [ref=l285]: "* 籍贯"
  - generic [ref=e285] [cursor=pointer]:
    - generic [ref=e286]: 请选择
    - list [ref=e287]:
      - listitem [ref=e288]:
        - textbox [ref=e289]
- generic [ref=sec3]:
  - generic [ref=l304]: "* 国籍"
  - generic [ref=e304] [cursor=pointer]:
    - generic [ref=e305]: 中国
    - list [ref=e306]:
      - listitem [ref=e307]:
        - textbox [ref=e308]: 中国
"""

# 展开后的快照：e103 / e285 的 list 里出现选项
EXPANDED = """\
- generic [ref=sec1]:
  - generic [ref=l103]: 面试站点
  - generic [ref=e103] [cursor=pointer]:
    - generic [ref=e105]: 请选择
    - list [ref=e106]:
      - listitem [ref=e110]:
        - generic: 合肥
      - listitem [ref=e111]:
        - generic: 上海
- generic [ref=sec2]:
  - generic [ref=l285]: "* 籍贯"
  - generic [ref=e285] [cursor=pointer]:
    - generic [ref=e286]: 请选择
    - list [ref=e287]:
      - listitem [ref=e290]:
        - generic: 安徽省
      - listitem [ref=e291]:
        - generic: 北京市
- generic [ref=sec3]:
  - generic [ref=l304]: "* 国籍"
  - generic [ref=e304] [cursor=pointer]:
    - generic [ref=e305]: 中国
    - list [ref=e306]:
      - listitem [ref=e307]:
        - textbox [ref=e308]: 中国
"""


class FakeCall:
    """模拟 MCP 调用：首次快照返回折叠态，后续快照返回展开态。"""

    def __init__(self):
        self.snaps = 0
        self.clicks: list[str] = []

    async def __call__(self, name, args=None):
        args = args or {}
        if name == "browser_snapshot":
            self.snaps += 1
            return (COLLAPSED if self.snaps == 1 else EXPANDED), False
        if name == "browser_click":
            self.clicks.append(args.get("target"))
            return "ok", False
        return "?", True


def _install_fake(monkeypatch, fake=None):
    fake = fake or FakeCall()
    for path in (
        "src.browser_mcp.client.call_tool",
        "src.browser_mcp.dropdown.call_tool",
        "src.tools.builtin.browser_probe_dropdowns.call_tool",
        "src.tools.builtin.browser_fill_dropdowns.call_tool",
    ):
        monkeypatch.setattr(path, fake)
    return fake


@pytest.mark.asyncio
async def test_probe_lists_unfilled_dropdowns(monkeypatch):
    fake = _install_fake(monkeypatch)
    res = await browser_probe_dropdowns.execute({"refs": []})
    assert not res.is_error
    # 未填的列出（含标签），已填的标注
    assert "面试站点" in res.output and "未填" in res.output
    assert "* 籍贯" in res.output
    assert "已填" in res.output and "* 国籍" in res.output
    # 不再展开点击获取选项
    assert fake.clicks == []
    assert fake.snaps == 1


@pytest.mark.asyncio
async def test_probe_handles_invalid_refs(monkeypatch):
    fake = _install_fake(monkeypatch)
    res = await browser_probe_dropdowns.execute({"refs": ["e103", "e999"]})
    assert "e999" in res.output and "无效 ref" in res.output
    assert "[e103]" in res.output
    assert fake.clicks == []


@pytest.mark.asyncio
async def test_fill_clicks_matching_options(monkeypatch):
    fake = _install_fake(monkeypatch)
    monkeypatch.setattr(
        "src.api.profile_storage.load",
        lambda: {"basic_info": {"hometown": "安徽省", "id_number": "110101199001011234"},
                 "masked_basic_fields": ["id_number"]},
    )
    res = await browser_fill_dropdowns.execute({
        "items": [
            {"ref": "e103", "value": "合肥"},
            {"ref": "e285", "data_key": "basic_info.hometown"},
            {"ref": "e999", "value": "x"},
            {"ref": "e304", "data_key": "basic_info.id_number"},
        ]
    })
    assert not res.is_error
    assert "已填写（2）" in res.output
    assert "[e103] → 合肥" in res.output
    assert "[e285] → 安徽省" in res.output
    # 无效 ref 跳过（未点击）
    assert "跳过（1）" in res.output and "e999" in res.output
    # data_key 敏感值脱敏：未匹配且不泄露真实值
    assert "未匹配（1）" in res.output
    assert "***" in res.output
    assert "110101199001011234" not in res.output
    # 点击序列：展开→选中 依次为 e103、e110、e285、e290、e304；e999 未点击
    assert fake.clicks == ["e103", "e110", "e285", "e290", "e304"]


# ---- 过滤型 combobox：展开无选项 → 输入搜索 → 按文本点击选项 → 点确定 ----

# 展开后的过滤型下拉框：只有 combobox + 过滤 textbox，选项不在可访问性快照里
FILTER_COLLAPSED = """\
- generic [ref=s1]:
  - generic [ref=lb]: 城市
  - combobox [expanded] [ref=e154] [cursor=pointer]:
    - textbox [active] [ref=e158]
"""

# 点选后出现的确定按钮弹层
CONFIRM_SNAP = """\
- generic [ref=pop]:
  - button "确定" [ref=cf]
"""


class FilterFakeCall:
    """过滤型下拉框流程模拟：验证→展开→输入→快照→文本点击→确定。"""

    def __init__(self, snapshots, find_result="[ref=optA]"):
        self._snaps = list(snapshots)
        self.clicks: list[str] = []
        self.types: list[tuple] = []
        self.finds: list[str] = []
        self.find_result = find_result

    async def __call__(self, name, args=None):
        args = args or {}
        if name == "browser_snapshot":
            return (self._snaps.pop(0) if self._snaps
                    else "### Snapshot\n```yaml\n- generic: 空\n```\n"), False
        if name == "browser_click":
            self.clicks.append(args.get("target"))
            return "ok", False
        if name == "browser_type":
            self.types.append((args.get("target"), args.get("text")))
            return "ok", False
        if name == "browser_find":
            self.finds.append(args.get("text"))
            return self.find_result, False
        if name == "browser_run_code_unsafe":
            return "ok", False
        return "?", True


@pytest.mark.asyncio
async def test_fill_filter_type_dropdown(monkeypatch):
    fake = FilterFakeCall(
        snapshots=[FILTER_COLLAPSED, FILTER_COLLAPSED, FILTER_COLLAPSED, CONFIRM_SNAP],
        find_result="- option 上海 [ref=optA]",
    )
    _install_fake(monkeypatch, fake)
    res = await browser_fill_dropdowns.execute({
        "items": [{"ref": "e154", "value": "上海"}]
    })
    assert not res.is_error
    assert "已填写（1）" in res.output
    assert "[e154] → 上海" in res.output
    # 向过滤输入框输入 → 文本定位点击选项 → 点确定
    assert fake.types == [("e158", "上海")]
    assert fake.finds == ["上海"]
    assert fake.clicks == ["e154", "optA", "cf"]
