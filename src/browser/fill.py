"""表单检测与自动填写。

从投递页表单中读取控件及其标签，对照集中式字段匹配表，
将已保存的个人信息（profile.json）填入能匹配的字段。

字段匹配（match_field）与报告生成（make_report）为纯函数，便于单测；
浏览器 I/O（detect_form / fill_form）通过 Playwright 完成。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from src.api import profile_storage

if TYPE_CHECKING:
    from playwright.async_api import Page

# 判定「表单已出现」的可填控件数量阈值
FORM_MIN_CONTROLS = 3

# ---- 字段匹配表（集中定义，可扩展）----
# 每一项：(标签关键词元组, 取值函数, 报告用键名)
# 取值函数从 profile 字典取真实值，无值返回 None。
# 顺序即优先级：更具体的标签（如「学历类型」）须排在更宽泛的标签（如「学历」）之前。

FIELD_MAP: list[tuple[tuple[str, ...], Callable[[dict], str | None], str]] = [
    (("证件类型",), lambda p: _get(p, ["basic_info", "id_type"]), "id_type"),
    (("证件号码", "身份证号", "身份证"), lambda p: _get(p, ["basic_info", "id_number"]), "id_number"),
    (("证件有效期",), lambda p: _get(p, ["basic_info", "id_valid_until"]), "id_valid_until"),
    (("姓名",), lambda p: _get(p, ["basic_info", "name"]), "name"),
    (("手机", "电话"), lambda p: _get(p, ["basic_info", "phone"]), "phone"),
    (("邮箱", "e-mail", "email"), lambda p: _get(p, ["basic_info", "email"]), "email"),
    (("性别",), lambda p: _get(p, ["basic_info", "gender"]), "gender"),
    (("年龄",), lambda p: _get(p, ["basic_info", "age"]), "age"),
    (("所在地", "现居", "居住地", "当前城市", "城市"), lambda p: _get(p, ["basic_info", "location"]), "location"),
    (("家乡",), lambda p: _get(p, ["basic_info", "hometown"]), "hometown"),
    (("学历类型",), lambda p: _first_list(p, "education", "degree_type"), "degree_type"),
    (("学历",), lambda p: _first_list(p, "education", "degree"), "degree"),
    (("学校", "院校", "毕业院校"), lambda p: _first_list(p, "education", "school_name"), "school_name"),
    (("专业",), lambda p: _first_list(p, "education", "major"), "major"),
    (("公司", "单位"), lambda p: _first_list(p, "internship", "company_name"), "company_name"),
    (("职位",), lambda p: _first_list(p, "internship", "position"), "position"),
    (("奖项", "荣誉"), lambda p: _first_list(p, "award", "award_name"), "award_name"),
    (("语言", "外语"), lambda p: _first_list(p, "language", "language"), "language"),
    (("自我评价", "自我介绍", "个人简介"), lambda p: _get(p, ["self_evaluation"]), "self_evaluation"),
]


def _get(profile: dict, path: list[str]) -> str | None:
    """按键路径取 profile 中的字符串值，无值返回 None。"""
    cur: object = profile
    for part in path:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, str) and cur else None


def _first_list(profile: dict, section: str, key: str) -> str | None:
    """取经历类分区第一条记录的指定字段值。"""
    items = profile.get(section) or []
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    value = first.get(key) if isinstance(first, dict) else None
    return value if isinstance(value, str) and value else None


def match_field(label_text: str, profile: dict) -> tuple[str, str] | None:
    """将控件标签对照匹配表，返回 (报告键名, 真实值)；无匹配或取值返回 None。

    归一化处理：去首尾空白、转小写。匹配到关键词但取值为空时，
    继续尝试匹配表中更宽泛的下一条。
    """
    if not label_text:
        return None
    text = label_text.strip().lower()
    for keywords, getter, key in FIELD_MAP:
        if any(kw.lower() in text for kw in keywords):
            value = getter(profile)
            if value:
                return (key, value)
    return None


def _mask_value(key: str, value: str, profile: dict) -> str:
    """对 masked_basic_fields 中标记的键，在报告中以 *** 显示。"""
    masked = set(profile.get("masked_basic_fields") or [])
    return "***" if key in masked else value


def make_report(filled: list[dict], unmatched: list[str], profile: dict) -> str:
    """生成填写报告文本，含已填字段、未匹配字段和下一步指引。"""
    lines: list[str] = []
    if filled:
        lines.append("已根据你的个人信息填写以下字段：")
        for f in filled:
            lines.append(f"- {f['label']}: {_mask_value(f['key'], f['value'], profile)}")
    else:
        lines.append("没有能根据个人信息自动填写的字段。")

    if unmatched:
        lines.append("以下字段未能自动填写，请在浏览器中手动补填：")
        for u in unmatched:
            lines.append(f"- {u}")

    lines.append("请检查表单无误后点击「提交」，完成后回复「已提交」。")
    return "\n".join(lines)


async def detect_form(page: "Page") -> bool:
    """启发式判断投递表单是否已出现：可填控件数达标且存在提交类按钮。"""
    try:
        info = await page.evaluate(
            """() => {
                const controls = document.querySelectorAll('input, select, textarea');
                const buttons = [...document.querySelectorAll(
                    'button, input[type="submit"], input[type="button"]')]
                    .filter(b => /提交|投递|申请/.test((b.textContent || b.value) || ''));
                return { controlCount: controls.length, submitCount: buttons.length };
            }"""
        )
    except Exception:
        return False
    return (
        info.get("controlCount", 0) >= FORM_MIN_CONTROLS
        and info.get("submitCount", 0) > 0
    )


async def _collect_controls(page: "Page") -> list[dict]:
    """通过一次页面内 JS 评估收集全部表单控件信息。"""
    try:
        return await page.evaluate(
            """() => {
                const controls = document.querySelectorAll('input, select, textarea');
                const result = [];
                controls.forEach((el, index) => {
                    let label = '';
                    if (el.getAttribute('aria-label')) {
                        label = el.getAttribute('aria-label');
                    } else if (el.id) {
                        const lbl = document.querySelector(`label[for="${el.id}"]`);
                        if (lbl) label = lbl.textContent.trim();
                    }
                    if (!label && el.closest('label')) {
                        label = el.closest('label').textContent.trim();
                    }
                    if (!label && el.placeholder) {
                        label = el.placeholder;
                    }
                    result.push({
                        index,
                        tag: el.tagName.toLowerCase(),
                        type: (el.type || '').toLowerCase(),
                        id: el.id || '',
                        name: el.name || '',
                        label: label.replace(/[*:：\\s]+$/g, '').trim(),
                    });
                });
                return result;
            }"""
        )
    except Exception:
        return []


async def _fill_control(page: "Page", control: dict, value: str) -> None:
    """按控件类型填入值。无法处理时抛异常，由调用方归入未匹配清单。"""
    loc = page.locator("input, select, textarea").nth(control["index"])
    tag = control["tag"]
    ctype = control["type"]

    if tag == "select":
        try:
            await loc.select_option(label=value)
        except Exception:
            await loc.select_option(value=value)
        return

    if tag == "textarea":
        await loc.fill(value)
        return

    if ctype in ("radio", "checkbox"):
        target = page.get_by_text(value, exact=False).first
        if await target.count() > 0:
            await target.click()
            return
        raise ValueError("该选项需人工选择")

    if ctype == "file":
        raise ValueError("文件上传需人工处理")

    await loc.fill(value)


async def fill_form(page: "Page", profile: dict | None = None) -> dict:
    """自动填写当前页面的表单，返回填写结果。

    Args:
        page: 当前页面。
        profile: 个人信息字典。缺省时从存储加载（生产路径）。

    Returns:
        字典含 filled（已填字段列表）、unmatched（未匹配/失败清单）、
        report（给用户的报告文本）。个人信息缺失时返回引导文本。
    """
    if profile is None:
        profile = profile_storage.load()
    if not profile:
        return {
            "filled": [],
            "unmatched": [],
            "report": "尚未保存个人信息，请先在「个人信息管理」页面填写并保存后再调用。",
        }

    filled: list[dict] = []
    unmatched: list[str] = []

    for control in await _collect_controls(page):
        label = control["label"]
        matched = match_field(label, profile)
        if matched is None:
            if label:
                unmatched.append(label)
            continue

        key, value = matched
        try:
            await _fill_control(page, control, value)
            filled.append({"label": label, "key": key, "value": value})
        except Exception:
            unmatched.append(f"{label}（自动填写失败，请手动补填）")

    return {
        "filled": filled,
        "unmatched": unmatched,
        "report": make_report(filled, unmatched, profile),
    }
