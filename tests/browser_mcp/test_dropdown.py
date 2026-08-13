"""下拉框识别、裁切、选项提取与匹配的单测。"""

from src.browser_mcp.dropdown import (
    crop_subtree,
    extract_options,
    find_dropdown_candidates,
    find_option_ref,
)

# 基于真实 zhiye.com 快照结构：含未填/已填下拉框、上传按钮、「至今」切换钮
SNAP = """\
### Snapshot
```yaml
- generic [ref=e3]:
  - generic [ref=e81]:
    - generic [ref=e91]:
      - generic [ref=e94]: 面试站点
      - generic [ref=e103] [cursor=pointer]:
        - generic [ref=e105]: 请选择
        - list [ref=e106]:
          - listitem [ref=e107]:
            - textbox [ref=e108]
- generic [ref=e274]:
  - generic [ref=e276]:
    - generic [ref=e277]: "* 籍贯"
    - generic [ref=e285] [cursor=pointer]:
      - generic [ref=e286]: 请选择
      - list [ref=e287]:
        - listitem [ref=e288]:
          - textbox [ref=e289]
- generic [ref=e296]:
  - generic [ref=e297]: "* 国籍Nationality/Region"
  - generic [ref=e304] [cursor=pointer]:
    - generic [ref=e305]: 中国
    - list [ref=e306]:
      - listitem [ref=e307]:
        - textbox [ref=e308]: 中国
      - generic: 中国
- generic [ref=e75] [cursor=pointer]:
  - generic [ref=e76]:
    - img "icon/上传" [ref=e78]
    - text: 拖拽或点击上传简历
- generic [ref=e862] [cursor=pointer]:
  - generic [ref=e863]: 至今
```
"""

# 展开后的下拉框子树（listitem 含 generic 文本）
EXPANDED_SNAP = """\
- generic [ref=d1] [cursor=pointer]:
  - generic [ref=d2]: 请选择
  - list [ref=d3]:
    - listitem [ref=d4]:
      - generic: 北京
    - listitem [ref=d5]:
      - generic: 上海
    - listitem [ref=d6]:
      - generic: 合肥
"""


# ---- find_dropdown_candidates ----

def test_find_dropdown_candidates():
    cands = find_dropdown_candidates(SNAP)
    by_ref = {c["ref"]: c for c in cands}
    # 识别出 3 个下拉框；上传按钮与「至今」切换钮被排除
    assert set(by_ref) == {"e103", "e285", "e304"}
    # 字段标签（同层前序兄弟）
    assert by_ref["e103"]["label"] == "面试站点"
    assert by_ref["e285"]["label"] == "* 籍贯"
    assert by_ref["e304"]["label"] == "* 国籍Nationality/Region"
    # 当前显示值与是否未填
    assert by_ref["e103"]["display"] == "请选择"
    assert by_ref["e103"]["is_empty"] is True
    assert by_ref["e285"]["display"] == "请选择"
    assert by_ref["e285"]["is_empty"] is True
    assert by_ref["e304"]["display"] == "中国"
    assert by_ref["e304"]["is_empty"] is False


def test_find_dropdown_candidates_excludes_non_dropdowns():
    refs = [c["ref"] for c in find_dropdown_candidates(SNAP)]
    # 上传简历区 / 「至今」切换钮不是下拉框
    assert "e75" not in refs
    assert "e862" not in refs


# ---- crop_subtree ----

def test_crop_subtree():
    crop = crop_subtree(SNAP, "e285")
    assert "请选择" in crop
    assert "[ref=e288]" in crop
    # 只含该下拉框子树，不含同层其他块
    assert "国籍" not in crop
    assert "面试站点" not in crop
    # ref 不存在
    assert crop_subtree(SNAP, "nope") == ""


# ---- extract_options ----

def test_extract_options_from_generic_listitems():
    opts = extract_options(EXPANDED_SNAP)
    assert [o["value"] for o in opts] == ["北京", "上海", "合肥"]
    assert [o["ref"] for o in opts] == ["d4", "d5", "d6"]


def test_extract_options_from_textbox_value():
    crop = crop_subtree(SNAP, "e304")
    assert extract_options(crop) == [
        {"value": "中国", "ref": "e307", "selected": False}
    ]


def test_extract_options_collapsed_returns_empty():
    # 未展开时 list 里只有搜索框（无文本），无选项
    crop = crop_subtree(SNAP, "e103")
    assert extract_options(crop) == []


# ---- 其他站点的 combobox 变体与可展开区块 ----

COMBOS_SNAP = """\
- generic [ref=e148]:
  - generic [ref=e149]: 性别
  - combobox [ref=e154] [cursor=pointer]
- generic [ref=e161]:
  - generic [ref=e162]: 年龄
  - textbox "年龄" [ref=e166]
- generic [ref=e181]:
  - generic [ref=e182]: 个人证件 *
  - generic [ref=e189]:
    - combobox [ref=e191] [cursor=pointer]:
      - generic [ref=e192]: 中国 - 居民身份证
    - textbox [ref=e199]
- generic [ref=e214]:
  - generic [ref=e215]: 期望工作地点
  - combobox [ref=e219]:
    - menubar [ref=e221]:
      - listitem [ref=e222]:
        - textbox "filter select" [ref=e224]
- generic [ref=e236] [cursor=pointer]:
  - generic [ref=e238]:
    - generic [ref=e239]:
      - generic [ref=e240]: 起止时间 *
      - generic [ref=e246]:
        - generic [ref=e247]:
          - generic [ref=e248]: YYYY
        - list [ref=e260]:
          - listitem [ref=e261]:
            - generic: 深层区块内容
"""


def test_combobox_variants_detected():
    by_ref = {c["ref"]: c for c in find_dropdown_candidates(COMBOS_SNAP)}
    # combobox 全部检出：纯 combobox、带 cursor=pointer、嵌套值、menubar/filter select
    assert "e154" in by_ref
    assert "e191" in by_ref
    assert "e219" in by_ref
    # 非下拉框排除：textbox、可展开区块 e236
    assert "e166" not in by_ref
    assert "e236" not in by_ref
    # 标签（同层前序兄弟）
    assert by_ref["e154"]["label"] == "性别"
    assert by_ref["e219"]["label"] == "期望工作地点"
    # 显示值与已填状态
    assert by_ref["e154"]["display"] == ""
    assert by_ref["e154"]["is_empty"] is True
    assert by_ref["e191"]["display"] == "中国 - 居民身份证"
    assert by_ref["e191"]["is_empty"] is False
    assert by_ref["e219"]["is_empty"] is True


# ---- find_option_ref ----

def test_find_option_ref_exact_and_contains():
    opts = [{"value": "北京", "ref": "d4"}, {"value": "上海", "ref": "d5"}]
    assert find_option_ref(opts, "北京") == ("d4", "北京")
    assert find_option_ref(opts, "海") == ("d5", "上海")
    assert find_option_ref(opts, "广州") == (None, None)


def test_find_option_ref_unclickable():
    # 选项无 ref → 返回 (None, 命中的选项值)
    assert find_option_ref([{"value": "深圳", "ref": ""}], "深圳") == (None, "深圳")
