/** 工具调用状态 */
export interface ToolCallState {
  toolId: string;
  toolName: string;
  argsJson: string;       // 累积的 JSON 参数字符串
  result: string | null;  // null = 尚未返回
  status: "running" | "done" | "error";
}

/** 单条消息（可携带工具调用） */
export interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallState[];  // 助手消息附带的工具调用
}

/** 完整会话（含消息列表） */
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
}

/** 会话摘要（不含消息列表） */
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
}

/** 当前视图类型 */
export type ViewType = "new_chat" | "resume" | "progress" | "conversation" | "profile";

/** 全局应用状态 */
export interface AppState {
  view: ViewType;
  conversations: ConversationSummary[];
  currentConversationId: string | null;
  messages: Message[];
  isStreaming: boolean;
  batchDeleteMode: boolean;
  selectedConvIds: Set<string>;
}

/** Reducer action 联合类型 */
export type AppAction =
  | { type: "SET_VIEW"; view: ViewType }
  | { type: "LOAD_CONVERSATIONS"; conversations: ConversationSummary[] }
  | { type: "ADD_CONVERSATION"; conversation: ConversationSummary }
  | { type: "SET_CURRENT_CONVERSATION"; id: string; messages: Message[] }
  | { type: "APPEND_MESSAGE"; message: Message }
  | { type: "UPDATE_LAST_MESSAGE"; delta: string }
  | { type: "SET_STREAMING"; isStreaming: boolean }
  | { type: "TOOL_START"; toolId: string; toolName: string }
  | { type: "TOOL_DELTA"; toolId: string; delta: string }
  | { type: "TOOL_END"; toolId: string }
  | { type: "TOOL_RESULT"; toolId: string; content: string; isError: boolean }
  | { type: "TOGGLE_BATCH_DELETE" }
  | { type: "TOGGLE_SELECT_CONVERSATION"; conversationId: string }
  | { type: "DELETE_CONVERSATIONS"; conversationIds: string[] };

// ========== 简历相关类型 ==========

export interface ResumeSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface Resume {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  blocks: Block[];
  connections: Connection[];
}

export type BlockType = "personal_info" | "content";

export interface BlockPosition {
  x: number;
  y: number;
}

export interface TextSpan {
  text: string;
  bold: boolean;
}

export interface PersonalInfoData {
  name: string;
  phone: string;
  email: string;
  location: string;
  photoUrl: string | null;
}

export type ContentCategory =
  | "项目经历"
  | "实习经历"
  | "教育经历"
  | "专业技能";

export interface ContentData {
  category: ContentCategory;
  timeSpan: string;
  spans: TextSpan[];
  bulletPoints: boolean;
}

export interface Block {
  id: string;
  type: BlockType;
  position: BlockPosition;
  personalInfo?: PersonalInfoData;
  content?: ContentData;
}

export interface Connection {
  id: string;
  fromBlockId: string;
  toBlockId: string;
}

export interface ResumeState {
  resumes: ResumeSummary[];
  currentResume: Resume | null;
  selectedBlockId: string | null;
  selectedConnectionId: string | null;
}

export type ResumeAction =
  | { type: "LOAD_RESUMES"; resumes: ResumeSummary[] }
  | { type: "SET_CURRENT_RESUME"; resume: Resume }
  | { type: "ADD_RESUME"; resume: Resume }
  | { type: "REMOVE_RESUME"; resumeId: string }
  | { type: "UPDATE_RESUME_NAME"; name: string }
  | { type: "ADD_BLOCK"; block: Block }
  | { type: "UPDATE_BLOCK"; block: Block }
  | { type: "DELETE_BLOCK"; blockId: string }
  | { type: "MOVE_BLOCK"; blockId: string; position: BlockPosition }
  | { type: "ADD_CONNECTION"; connection: Connection }
  | { type: "DELETE_CONNECTION"; connectionId: string }
  | { type: "SELECT_BLOCK"; blockId: string }
  | { type: "SELECT_CONNECTION"; connectionId: string }
  | { type: "CLEAR_SELECTION" };

// ========== 个人信息管理相关类型 ==========

/** 基本信息（个人证件为类型 + 号码 + 有效期三字段） */
export interface BasicInfo {
  name: string;
  phone: string;
  email: string;
  gender: string;
  age: string;
  location: string;
  id_type: string;
  id_number: string;
  id_valid_until: string;
  hometown: string;
}

/** 教育经历单条记录（id 仅前端使用，保存时剥离） */
export interface EducationEntry {
  id: string;
  start_time: string;
  end_time: string;
  school: string;
  degree: string;
  degree_type: string;
  major: string;
}

/** 实习经历单条记录 */
export interface InternshipEntry {
  id: string;
  start_time: string;
  end_time: string;
  company: string;
  position: string;
  description: string;
}

/** 项目经历单条记录 */
export interface ProjectEntry {
  id: string;
  start_time: string;
  end_time: string;
  name: string;
  role: string;
  link: string;
  description: string;
}

/** 奖项单条记录 */
export interface AwardEntry {
  id: string;
  time: string;
  name: string;
  description: string;
}

/** 语言能力单条记录 */
export interface LanguageEntry {
  id: string;
  language: string;
  proficiency: string;
}

/** 经历类分区的键 */
export type ProfileSectionKey =
  | "education"
  | "internship"
  | "project"
  | "award"
  | "language";

/** 各分区单条记录的联合类型 */
export type ProfileEntry =
  | EducationEntry
  | InternshipEntry
  | ProjectEntry
  | AwardEntry
  | LanguageEntry;

/** 整份个人信息字典（前端表单状态，条目含局部 id） */
export interface PersonalProfile {
  basic_info: BasicInfo;
  education: EducationEntry[];
  internship: InternshipEntry[];
  project: ProjectEntry[];
  award: AwardEntry[];
  language: LanguageEntry[];
  self_evaluation: string;
  /** 已勾选「脱敏」的基本信息字段键（agent 读取时该字段值以 *** 替换） */
  masked_basic_fields: string[];
}

/** 持久化 / 传给后端的字典结构（不含前端条目 id），与 data/personal/profile.json 一致 */
export type SavableProfile = {
  basic_info: BasicInfo;
  education: Omit<EducationEntry, "id">[];
  internship: Omit<InternshipEntry, "id">[];
  project: Omit<ProjectEntry, "id">[];
  award: Omit<AwardEntry, "id">[];
  language: Omit<LanguageEntry, "id">[];
  self_evaluation: string;
  masked_basic_fields: string[];
};
