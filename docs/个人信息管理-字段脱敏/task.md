# 个人信息字段脱敏 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/api/profile_storage.py` | empty_profile 顶层加 `masked_basic_fields` |
| 修改 | `src/api/profile_routes.py` | PersonalProfileBody 加可选 `masked_basic_fields` |
| 修改 | `src/tools/builtin/get_personal_info.py` | 重写：脱敏读取工具 |
| 修改 | `frontend/src/types.ts` | PersonalProfile / SavableProfile 加 `masked_basic_fields` |
| 修改 | `frontend/src/components/profile/profileFieldConfigs.ts` | emptyProfile 加空数组 |
| 修改 | `frontend/src/components/ProfileContext.tsx` | TOGGLE_MASKED_FIELD action + reducer |
| 修改 | `frontend/src/components/profile/BasicInfoSection.tsx` | 字段旁加脱敏 checkbox |
| 修改 | `frontend/src/components/ProfilePage.tsx` | 加载/保存处理 mask |

Python 解释器：`D:\coding\Anaconda\envs\agent\python.exe`（所有 Python 验证用此路径，工作目录为项目根）。

## T1: 后端支持 masked_basic_fields

**文件：** `src/api/profile_storage.py`、`src/api/profile_routes.py`
**依赖：** 无
**步骤：**
1. `profile_storage.empty_profile()` 返回字典顶层加 `"masked_basic_fields": []`
2. `profile_routes.PersonalProfileBody` 加字段 `masked_basic_fields: list[str] = []`

**验证：**
```
D:/coding/Anaconda/envs/agent/python.exe -c "from src.api import profile_storage; from src.api.profile_routes import PersonalProfileBody; assert 'masked_basic_fields' in profile_storage.empty_profile(); b=PersonalProfileBody.model_validate({'basic_info':{},'education':[],'internship':[],'project':[],'award':[],'language':[],'self_evaluation':'','masked_basic_fields':['phone']}); assert b.masked_basic_fields==['phone']; print('T1 OK')"
```

## T2: 实现 getPersonalInfo 工具

**文件：** `src/tools/builtin/get_personal_info.py`
**依赖：** T1
**步骤：**
1. 重写整个文件，删除原坏桩（含无效的 `@tool` 无参装饰与多余 import）
2. 定义空参数模型 `class Params(BaseModel): pass`
3. `@tool(name="getPersonalInfo", description=...)` 装饰 async 函数
4. 函数内：`profile_storage.load()` → None 时返回友好提示；否则 `data.pop("masked_basic_fields", [])`，遍历配置将 `basic_info` 中非空值字段置 `"***"`，`json.dumps(ensure_ascii=False, indent=2)` 返回
5. 确认从 `src.api import profile_storage` 不产生循环导入（该模块仅依赖标准库）

**验证：**
```
D:/coding/Anaconda/envs/agent/python.exe -c "
import asyncio
from src.tools.registry import ToolRegistry
r = ToolRegistry.get_instance()
r.discover('src.tools.builtin')
t = r.get_tool('getPersonalInfo')
assert t is not None, '未注册'
res = asyncio.run(r.execute('getPersonalInfo', {}))
print(res.output)
print('is_error:', res.is_error)
"
```
期望：`getPersonalInfo` 存在；输出为 JSON 且 `is_error=False`；若当前 profile.json 未含 masked_basic_fields，输出中 `basic_info.phone` 仍为原值（旧档兼容）。

## T3: 前端类型与 Context 支持脱敏状态

**文件：** `frontend/src/types.ts`、`frontend/src/components/profile/profileFieldConfigs.ts`、`frontend/src/components/ProfileContext.tsx`
**依赖：** 无
**步骤：**
1. `types.ts`：`PersonalProfile` 与 `SavableProfile` 各加 `masked_basic_fields: string[]`
2. `profileFieldConfigs.ts`：`emptyProfile()` 返回对象加 `masked_basic_fields: []`
3. `ProfileContext.tsx`：`ProfileAction` 联合类型加 `{ type: "TOGGLE_MASKED_FIELD"; key: string; checked: boolean }`
4. reducer 加 `TOGGLE_MASKED_FIELD` case：checked 且不存在则追加，未 checked 则移除，返回新数组（保持不可变更新）

**验证：** `cd frontend && npx tsc -b` 无类型错误（若 tsconfig 有 noEmit 限制则改用项目 build 脚本的 tsc 步骤）。

## T4: BasicInfoSection 加脱敏勾选框

**文件：** `frontend/src/components/profile/BasicInfoSection.tsx`
**依赖：** T3
**步骤：**
1. 外层元素从 `<label>` 改为 `<div>`（避免与内部 checkbox 的 label 嵌套）
2. 字段标签行改为 flex 布局：左侧显示 `field.label`，右侧加 `「脱敏」` checkbox
3. checkbox `checked` 取 `masked_basic_fields.includes(field.key)`，onChange dispatch `TOGGLE_MASKED_FIELD`
4. 保持原输入控件（select/input）与 `SET_BASIC_FIELD` 逻辑不变

**验证：** `cd frontend && npx tsc -b` 通过；`npm run dev` 下基本信息区每个字段旁出现「脱敏」checkbox，勾选后 React DevTools 中 `masked_basic_fields` 随之更新。

## T5: ProfilePage 加载/保存处理 mask

**文件：** `frontend/src/components/ProfilePage.tsx`
**依赖：** T3、T4
**步骤：**
1. `toStateProfile`：返回对象加 `masked_basic_fields: saved.masked_basic_fields ?? []`
2. `toSavableProfile`：返回对象加 `masked_basic_fields: state.masked_basic_fields`

**验证：** `npx tsc -b` 通过；`npm run dev` 下勾选若干字段保存后 `cat data/personal/profile.json`，顶层含 `masked_basic_fields`；刷新页面勾选状态保持。

## T6: 端到端验收

**文件：** 全部
**依赖：** T1–T5
**步骤：**
1. 启动后端（`python src/api/main.py` 或项目启动方式）与前端（`npm run dev`）
2. 按 `docs/个人信息管理-字段脱敏/checklist.md` 逐项执行并记录证据

**验证：** checklist 全部通过。

## 执行顺序

```
T1 → T2
T3 → T4 → T5
T1/T2 与 T3/T4/T5 两条链可并行，T6 最后（依赖全部）
```
