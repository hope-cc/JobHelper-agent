"""parse_snapshot 增强解析的单测（值/状态/选项/radio 选项关联）。"""

from src.browser_mcp.fill import parse_snapshot


def _element(elements, name):
    return next(e for e in elements if e.get("name") == name)


def test_textbox_value_suffix():
    els = parse_snapshot('- textbox "姓名" [ref=e4]: 张三')
    assert _element(els, "姓名")["value"] == "张三"


def test_textbox_quoted_value_unquoted():
    els = parse_snapshot('- textbox "手机" [ref=e6]: "13800000000"')
    assert _element(els, "手机")["value"] == "13800000000"


def test_textbox_empty_value():
    els = parse_snapshot('- textbox "姓名" [ref=e4]')
    assert _element(els, "姓名")["value"] == ""


def test_combobox_options_and_selected():
    els = parse_snapshot(
        '- combobox "学历" [ref=e8]:\n'
        '  - option "请选择" [selected]\n'
        '  - option "本科"'
    )
    c = _element(els, "学历")
    assert [o["value"] for o in c["options"]] == ["请选择", "本科"]
    assert c["options"][0]["selected"] is True
    assert c["options"][1]["selected"] is False


def test_checkbox_checked():
    els = parse_snapshot('- checkbox "同意协议" [checked] [ref=e13]')
    assert _element(els, "同意协议")["selected"] is True


def test_radio_option_labels_from_text_siblings():
    els = parse_snapshot(
        '- generic [ref=e9]:\n'
        '  - text: 性别\n'
        '  - radio "性别 男 女" [ref=e10]\n'
        '  - text: 男\n'
        '  - radio [ref=e11]\n'
        '  - text: 女'
    )
    radios = [e for e in els if e["role"] == "radio"]
    assert [r["options"][0]["value"] for r in radios] == ["男", "女"]


def test_old_format_compatible():
    els = parse_snapshot('[ref=2] textbox "姓名" [required]')
    assert els[0]["ref"] == "2"
    assert els[0]["role"] == "textbox"
    assert els[0]["name"] == "姓名"
    assert els[0]["value"] == ""
    assert els[0]["selected"] is False
    assert els[0]["options"] == []


def test_new_format_role_before_ref():
    els = parse_snapshot('textbox [ref=2]: 姓名')
    assert els[0]["role"] == "textbox"
    assert els[0]["name"] == "姓名"


def test_option_lines_without_combobox_ignored():
    els = parse_snapshot('- option "本科"\n- textbox "姓名" [ref=e4]')
    assert len(els) == 1 and els[0]["ref"] == "e4"


def test_no_ref_line_ignored():
    els = parse_snapshot('- text: 姓名\n- Page URL: x')
    assert els == []
