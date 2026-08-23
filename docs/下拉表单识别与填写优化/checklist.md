# 下拉框探测与填写优化 Checklist

> 每项运行代码或观察行为验证，聚焦系统行为。

## 实现完整性
- [ ] [find_popup] 能从全局快照定位到弹层节点（验证：`python -c` 调用 find_popup 解析 snapshot_example.txt，返回 ref=e1739 节点）
- [ ] [popup_options] 从弹层提取出纯文本选项列表，不含 ref/缩进/DOM 结构（验证：脚本断言返回 "北京市"、"安徽省"，且不含 "全国/全部省市/已选地区/清空已选/取消/确定"）
- [ ] [popup_filter_ref] 弹层内识别搜索输入框（验证：snapshot_example.txt → 返回 e1745）
- [ ] [popup_confirm_ref / popup_dismiss_ref] 弹层内识别「确定/取消」（验证：分别返回 e2120 / e2116）
- [ ] [expand_popup] 点击展开+全局快照+弹层定位封装（验证：模拟调用无语法错误；真实连接时返回弹层）
- [ ] [probe] 仅对未填下拉框逐个展开、取特征、收起（验证：调用后浏览器无残留弹层）
- [ ] [fill L1] 弹层选项匹配并点击（精确后包含匹配）
- [ ] [fill L2] 弹层含搜索框时输入过滤→重新快照→点选
- [ ] [fill L3] 输入后按回车（browser_press_key 或 JS 兜底）
- [ ] [fill L4] 无弹层/无效的文本定位兜底 select_by_text
- [ ] [fill] 展开失败/无效 ref → 计入 skipped/failed，不中断其余 item

## 集成
- [ ] probe 返回的 ref + label 与 fill 的 items 输入打通（验证：probe 输出格式含 `- [ref] label（未填）：选项清单`）
- [ ] 敏感字段：fill 返回报告中对敏感 data_key 显示 `***`（验证：profile 带 masked_basic_fields，value 取自字段时报告脱敏）
- [ ] prompt.py 步骤7/8 文案与 _SUBMIT_FLOW_NEXT 提醒文本已同步（验证：grep 步骤7 含「选项清单」、步骤8 含「label+选项」）

## 编译与测试
- [ ] 四个改动文件 `python.exe -m py_compile` 全部通过
- [ ] 纯解析测试脚本断言全部通过（find_popup / popup_options / filter/confirm/dismiss）

## 端到端场景
- [ ] 场景 1（zhiye 意向工作地点）：agent 调用 browser_probe_dropdowns → 逐个展开「意向工作地点」等未填下拉框 → 返回含「北京市/天津市/…」选项清单 → 填该类弹层即使站点无原生 select 也返回选项；随后 browser_fill_dropdowns 依据 `data_key=…` 选中目标省并点击「确定」，报告显示 filled。
- [ ] 场景 2（边界）：页面无任何非标准可选下拉框 → probe 返回「没有未填写的下拉框」；fill 传入无效 ref → 记 skipped。
- [ ] 场景 3（填写多形态）：存在「输入+点确定」型站点下拉 → L2 生效；存在「输入+回车」型 → L3 生效，不会停留在 L1 失败即停。