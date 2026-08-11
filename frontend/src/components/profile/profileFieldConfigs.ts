import type {
  BasicInfo,
  PersonalProfile,
  ProfileEntry,
  ProfileSectionKey,
} from "../../types";

/**
 * 字段配置：驱动表单渲染，也是「新增字段」的唯一入口。
 *
 * 新增一个字段时：
 * 1. 在对应分区的字段配置数组里加一行（key 为字典键名，label 为界面标签）
 * 2. 若是基本信息，同步在 types.ts 的 BasicInfo 里加对应属性；
 *    若是经历类条目，同步在 types.ts 对应 Entry 接口里加属性。
 */
export interface ProfileFieldConfig {
  /** 字段键（英文 snake_case，即保存到 JSON 的键名） */
  key: string;
  /** 界面显示标签 */
  label: string;
  type: "text" | "textarea" | "select";
  /** type 为 select 时的选项 */
  options?: string[];
  /** 是否占满整行（如描述、自我评价） */
  span?: boolean;
}

export const BASIC_INFO_FIELDS: ProfileFieldConfig[] = [
  { key: "name", label: "姓名", type: "text" },
  { key: "phone", label: "手机", type: "text" },
  { key: "email", label: "邮箱", type: "text" },
  { key: "gender", label: "性别", type: "select", options: ["男", "女", "其他"] },
  { key: "age", label: "年龄", type: "text" },
  { key: "location", label: "所在地点", type: "text" },
  {
    key: "id_type",
    label: "证件类型",
    type: "select",
    options: ["身份证", "护照", "港澳通行证", "台湾居民来往大陆通行证", "其他"],
  },
  { key: "id_number", label: "证件号码", type: "text" },
  { key: "id_valid_until", label: "有效期", type: "text" },
  { key: "hometown", label: "家乡", type: "text" },
];

export const EDUCATION_FIELDS: ProfileFieldConfig[] = [
  { key: "start_time", label: "开始时间", type: "text" },
  { key: "end_time", label: "结束时间", type: "text" },
  { key: "school", label: "学校名称", type: "text" },
  {
    key: "degree",
    label: "学历",
    type: "select",
    options: ["初中及以下", "高中", "大专", "本科", "硕士", "博士"],
  },
  {
    key: "degree_type",
    label: "学历类型",
    type: "select",
    options: ["统招", "全日制", "专升本", "自考", "成人教育", "网络教育", "函授", "其他"],
  },
  { key: "major", label: "专业", type: "text" },
];

export const INTERNSHIP_FIELDS: ProfileFieldConfig[] = [
  { key: "start_time", label: "开始时间", type: "text" },
  { key: "end_time", label: "结束时间", type: "text" },
  { key: "company", label: "公司名称", type: "text" },
  { key: "position", label: "职位名称", type: "text" },
  { key: "description", label: "描述", type: "textarea", span: true },
];

export const PROJECT_FIELDS: ProfileFieldConfig[] = [
  { key: "start_time", label: "开始时间", type: "text" },
  { key: "end_time", label: "结束时间", type: "text" },
  { key: "name", label: "项目名称", type: "text" },
  { key: "role", label: "项目角色", type: "text" },
  { key: "link", label: "项目链接", type: "text" },
  { key: "description", label: "描述", type: "textarea", span: true },
];

export const AWARD_FIELDS: ProfileFieldConfig[] = [
  { key: "time", label: "获奖时间", type: "text" },
  { key: "name", label: "获奖名称", type: "text" },
  { key: "description", label: "描述", type: "textarea", span: true },
];

export const LANGUAGE_FIELDS: ProfileFieldConfig[] = [
  {
    key: "language",
    label: "语言",
    type: "select",
    options: ["中文", "英语", "日语", "韩语", "法语", "德语", "西班牙语", "其他"],
  },
  {
    key: "proficiency",
    label: "精通程度",
    type: "select",
    options: ["入门", "一般", "良好", "精通", "母语"],
  },
];

/** 从字段配置构造空的基本信息对象。 */
export function emptyBasicInfo(): BasicInfo {
  return Object.fromEntries(
    BASIC_INFO_FIELDS.map((f) => [f.key, ""])
  ) as unknown as BasicInfo;
}

/** 空默认的整份个人信息（进入页面、保存前回填时的兜底结构）。 */
export function emptyProfile(): PersonalProfile {
  return {
    basic_info: emptyBasicInfo(),
    education: [],
    internship: [],
    project: [],
    award: [],
    language: [],
    self_evaluation: "",
    masked_basic_fields: [],
  };
}

/** 从字段配置构造一条空的经历类记录（含前端局部 id，保存时剥离）。 */
export function createEmptyEntry(
  _section: ProfileSectionKey,
  fields: ProfileFieldConfig[]
): ProfileEntry {
  const entry: Record<string, string> = { id: crypto.randomUUID() };
  for (const f of fields) entry[f.key] = "";
  return entry as unknown as ProfileEntry;
}
