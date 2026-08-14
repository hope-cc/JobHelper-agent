import type {
  BasicInfo,
  BasicFieldSchema,
  PersonalProfile,
  ProfileEntry,
  ProfileSectionKey,
} from "../../types";

/**
 * 经历类分区（教育/奖项/语言）仍由代码预定义字段。
 * 基本信息区字段改为用户自定义，DEFAULT_BASIC_FIELDS 仅作为首次加载时的默认 schema。
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

/** 基本信息默认字段 schema（用户未改动时的初始/兜底值，键名与历史数据一致）。 */
export const DEFAULT_BASIC_FIELDS: BasicFieldSchema[] = [
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

/** 从默认字段配置构造空的基本信息对象。 */
export function emptyBasicInfo(): BasicInfo {
  return Object.fromEntries(
    DEFAULT_BASIC_FIELDS.map((f) => [f.key, ""])
  ) as BasicInfo;
}

/** 空默认的整份个人信息（进入页面、保存前回填时的兜底结构）。 */
export function emptyProfile(): PersonalProfile {
  return {
    basic_fields_schema: DEFAULT_BASIC_FIELDS.map((f) => ({ ...f })),
    basic_info: emptyBasicInfo(),
    education: [],
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

/**
 * 根据用户填写的标签生成稳定键：
 * - 中文可直接作为键（Python/JSON/`basic_info.<key>` 路径解析均兼容）
 * - 清洗点号、空白、换行等会破坏路径解析的字符 → 下划线
 * - 与已有键冲突时追加 _2、_3 序号保证唯一
 */
export function sanitizeFieldKey(label: string, existingKeys: string[]): string {
  const cleaned = label
    .trim()
    .replace(/[.\s]+/g, "_")
    .replace(/_+/g, "_");
  if (!cleaned) {
    return `field_${existingKeys.length + 1}`;
  }
  let key = cleaned;
  let n = 2;
  const used = new Set(existingKeys);
  while (used.has(key)) {
    key = `${cleaned}_${n}`;
    n += 1;
  }
  return key;
}
