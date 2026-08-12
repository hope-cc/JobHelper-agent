"""简历 PDF 扫描与上传控件识别的单测。"""

from src.browser_mcp.upload import find_upload_control, list_resume_pdfs


def test_list_resume_pdfs_returns_sorted_pdfs():
    pdfs = list_resume_pdfs()
    assert isinstance(pdfs, list)
    assert all(p.suffix == ".pdf" for p in pdfs)
    # 修改时间倒序
    times = [p.stat().st_mtime for p in pdfs]
    assert times == sorted(times, reverse=True)


def test_find_upload_control_first_match():
    els = [
        {"ref": "e1", "role": "button", "name": "提交申请"},
        {"ref": "e2", "role": "button", "name": "上传简历"},
        {"ref": "e3", "role": "button", "name": "简历文件"},
    ]
    assert find_upload_control(els)["ref"] == "e2"


def test_find_upload_control_choose_file_and_drag():
    # 真实场景：小米表单上传控件是按钮"选择文件"；拖拽区整块作为按钮也可点击触发
    els = [
        {"ref": "e101", "role": "button", "name": ""},
        {"ref": "e106", "role": "button", "name": "选择文件"},
    ]
    assert find_upload_control(els)["ref"] == "e106"
    zone = find_upload_control(
        [{"ref": "e1", "role": "button", "name": "将你的简历拖拽到此处、选择文件"}]
    )
    assert zone and zone["ref"] == "e1"


def test_find_upload_control_none():
    assert find_upload_control([{"ref": "e1", "role": "button", "name": "提交申请"}]) is None
    assert find_upload_control([]) is None
