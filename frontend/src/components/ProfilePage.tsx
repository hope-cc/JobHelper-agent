import { useEffect, useState } from "react";
import { ProfileProvider, useProfileState, useProfileDispatch } from "./ProfileContext";
import * as api from "../api/profileClient";
import BasicInfoSection from "./profile/BasicInfoSection";
import EntrySection from "./profile/EntrySection";
import SelfEvaluationSection from "./profile/SelfEvaluationSection";
import {
  AWARD_FIELDS,
  DEFAULT_BASIC_FIELDS,
  EDUCATION_FIELDS,
  LANGUAGE_FIELDS,
} from "./profile/profileFieldConfigs";
import type { PersonalProfile, SavableProfile } from "../types";

/** 后端返回的字典（无 id）→ 前端状态（条目补上局部 id）；基本信息字段 schema 缺失时回退默认预设。 */
function toStateProfile(saved: SavableProfile): PersonalProfile {
  return {
    basic_fields_schema:
      saved.basic_fields_schema?.length
        ? saved.basic_fields_schema
        : DEFAULT_BASIC_FIELDS,
    basic_info: saved.basic_info ?? {},
    education: (saved.education ?? []).map((e) => ({
      ...e,
      id: crypto.randomUUID(),
    })),
    award: (saved.award ?? []).map((e) => ({
      ...e,
      id: crypto.randomUUID(),
    })),
    language: (saved.language ?? []).map((e) => ({
      ...e,
      id: crypto.randomUUID(),
    })),
    self_evaluation: saved.self_evaluation ?? "",
    masked_basic_fields: saved.masked_basic_fields ?? [],
  };
}

/** 前端状态 → 持久化字典（剥离条目 id，保证 JSON 干净）。 */
function toSavableProfile(state: PersonalProfile): SavableProfile {
  return {
    basic_fields_schema: state.basic_fields_schema,
    basic_info: state.basic_info,
    education: state.education.map(({ id: _id, ...rest }) => rest),
    award: state.award.map(({ id: _id, ...rest }) => rest),
    language: state.language.map(({ id: _id, ...rest }) => rest),
    self_evaluation: state.self_evaluation,
    masked_basic_fields: state.masked_basic_fields,
  };
}

function ProfilePageInner() {
  const state = useProfileState();
  const dispatch = useProfileDispatch();
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  useEffect(() => {
    api
      .getPersonal()
      .then((saved) =>
        dispatch({ type: "LOAD_PROFILE", profile: toStateProfile(saved) })
      )
      .catch((err) => console.error("加载个人信息失败:", err));
  }, [dispatch]);

  async function handleSave() {
    setSaving(true);
    setNotice(null);
    try {
      await api.savePersonal(toSavableProfile(state));
      setNotice({ type: "success", text: "保存成功" });
    } catch (err) {
      setNotice({
        type: "error",
        text: `保存失败: ${(err as Error).message}`,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-6 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-800">个人信息管理</h1>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-md transition"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>

        {notice && (
          <div
            className={`px-4 py-2 rounded-md text-sm ${
              notice.type === "success"
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {notice.text}
          </div>
        )}

        <BasicInfoSection />
        <EntrySection
          title="教育经历"
          section="education"
          fields={EDUCATION_FIELDS}
        />
        <EntrySection title="奖项" section="award" fields={AWARD_FIELDS} />
        <EntrySection
          title="语言能力"
          section="language"
          fields={LANGUAGE_FIELDS}
        />
        <SelfEvaluationSection />
      </div>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <ProfileProvider>
      <ProfilePageInner />
    </ProfileProvider>
  );
}
