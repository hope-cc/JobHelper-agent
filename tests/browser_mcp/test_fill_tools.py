"""脱敏取值与控件判定的单测。"""

from src.browser_mcp.fill import (
    display_value,
    find_radio_ref,
    is_fillable,
    is_option_el,
    is_upload_candidate,
    match_combobox_value,
    parse_snapshot,
    resolve_profile_value,
)


def _profile():
    return {
        "basic_info": {
            "name": "张三",
            "phone": "13800000000",
            "id_number": "440101199001011234",
            "gender": "男",
        },
        "education": [
            {"school_name": "清华", "major": "计算机"},
            {"school_name": "北大", "major": "软件"},
        ],
        "self_evaluation": "认真负责",
        "masked_basic_fields": ["phone", "id_number"],
    }


# ---- resolve_profile_value ----

def test_resolve_basic_info():
    assert resolve_profile_value(_profile(), "basic_info.name") == "张三"


def test_resolve_list_index():
    assert resolve_profile_value(_profile(), "education[0].school_name") == "清华"
    assert resolve_profile_value(_profile(), "education[1].major") == "软件"


def test_resolve_top_level():
    assert resolve_profile_value(_profile(), "self_evaluation") == "认真负责"


def test_resolve_missing_and_empty():
    p = _profile()
    p["basic_info"]["email"] = ""
    assert resolve_profile_value(p, "basic_info.email") is None
    assert resolve_profile_value(p, "basic_info.nonexist") is None
    assert resolve_profile_value(p, "education[5].major") is None
    assert resolve_profile_value(p, "education[0].gpa") is None
    assert resolve_profile_value(p, "bad.key") is None
    assert resolve_profile_value(p, "") is None
    assert resolve_profile_value(None, "basic_info.name") is None


# ---- display_value（脱敏显示）----

def test_display_masks_sensitive():
    p = _profile()
    assert display_value("basic_info.phone", "13800000000", p) == "***"
    assert display_value("basic_info.id_number", "440101199001011234", p) == "***"


def test_display_keeps_normal():
    p = _profile()
    assert display_value("basic_info.name", "张三", p) == "张三"
    assert display_value("education[0].school_name", "清华", p) == "清华"
    assert display_value("self_evaluation", "认真负责", p) == "认真负责"


# ---- match_combobox_value ----

def test_match_combobox_exact():
    options = [{"value": "本科"}, {"value": "硕士"}]
    assert match_combobox_value(options, "本科") == "本科"


def test_match_combobox_contains():
    assert match_combobox_value([{"value": "本科学历"}], "本科") == "本科学历"


def test_match_combobox_none():
    assert match_combobox_value([{"value": "本科"}], "高中") is None
    assert match_combobox_value([], "本科") is None


# ---- 控件判定 ----

def test_is_upload_candidate():
    assert is_upload_candidate({"role": "button", "name": "选择文件"})
    assert is_upload_candidate({"role": "button", "name": "上传简历"})
    assert is_upload_candidate({"role": "button", "name": "简历文件"})
    assert is_upload_candidate({"role": "button", "name": "将你的简历拖拽到此处、选择文件"})
    assert is_upload_candidate({"role": "file", "name": "简历文件"})
    # 动作按钮排除
    assert not is_upload_candidate({"role": "button", "name": "提交简历"})
    assert not is_upload_candidate({"role": "button", "name": "提交申请"})
    # 非按钮 / 空名
    assert not is_upload_candidate({"role": "generic", "name": "选择文件"})
    assert not is_upload_candidate({"role": "button", "name": ""})


def test_is_fillable_and_option():
    assert is_fillable({"role": "textbox"})
    assert is_fillable({"role": "combobox"})
    assert not is_fillable({"role": "checkbox"})
    assert is_option_el({"role": "radio"})
    assert is_option_el({"role": "checkbox"})
    assert not is_option_el({"role": "textbox"})


# ---- find_radio_ref（从真实快照结构推导单选选项）----

def test_find_radio_ref_from_snapshot():
    els = parse_snapshot(
        '- generic [ref=g1]:\n'
        '  - text: 性别\n'
        '  - radio "性别 男 女" [ref=a1]\n'
        '  - text: 男\n'
        '  - radio [ref=a2]\n'
        '  - text: 女'
    )
    radios = [e for e in els if e["role"] == "radio"]
    assert [r["options"][0]["value"] for r in radios] == ["男", "女"]
    assert find_radio_ref(els, "男") == "a1"
    assert find_radio_ref(els, "女") == "a2"
    assert find_radio_ref(els, "未知") is None
