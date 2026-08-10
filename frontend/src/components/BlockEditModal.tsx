import { useState, useRef, useCallback } from "react";
import { useResumeDispatch } from "./ResumeContext";
import * as api from "../api/resumeClient";
import type { Block, ContentCategory, TextSpan } from "../types";

interface BlockEditModalProps {
  block: Block;
  resumeId: string;
  onClose: () => void;
}

// ---- 工具函数：spans ↔ HTML 互转 ----

function spansToHtml(spans: TextSpan[]): string {
  if (!spans || spans.length === 0) return "";
  return spans
    .map((s) => {
      // 先按换行符拆分，每段转义后用 <br> 连接
      const parts = s.text.split("\n").map((p) => escapeHtml(p));
      const html = parts.join("<br>");
      return s.bold ? `<b>${html}</b>` : html;
    })
    .join("");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * 从 contentEditable 的 HTML 解析回 TextSpan[]。
 * 只保留 <b>/<strong> 作为加粗标记，忽略其他标签。
 */
function htmlToSpans(html: string): TextSpan[] {
  // 移除 <br> 和块级标签，替换为换行符
  let text = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(div|p|li|h[1-6])>/gi, "\n")
    .replace(/<[^>]+>/g, ""); // 这一步会丢掉加粗信息

  // 用更精细的方式：遍历 DOM
  const div = document.createElement("div");
  div.innerHTML = html;
  return extractSpans(div);
}

function extractSpans(node: Node): TextSpan[] {
  const result: TextSpan[] = [];
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_ALL);

  let currentText = "";
  let currentBold = false;

  function flush() {
    if (currentText) {
      result.push({ text: currentText, bold: currentBold });
      currentText = "";
    }
  }

  let n: Node | null = walker.firstChild();
  while (n) {
    if (n.nodeType === Node.TEXT_NODE) {
      const isBold = isInsideBold(n);
      if (isBold !== currentBold) {
        flush();
        currentBold = isBold;
      }
      currentText += n.textContent || "";
    } else if (n.nodeName === "BR") {
      flush();
      currentBold = false;
      currentText = "\n";
      flush();
    } else if (n.nodeName === "DIV" || n.nodeName === "P" || n.nodeName === "LI") {
      flush();
      if (result.length > 0) {
        currentBold = false;
        currentText = "\n";
        flush();
      }
    }
    n = walker.nextNode();
  }
  flush();

  // 合并连续的相同 bold 状态的 span
  return result.filter((s) => s.text.length > 0);
}

function isInsideBold(node: Node): boolean {
  let parent = node.parentElement;
  while (parent) {
    if (
      parent.tagName === "B" ||
      parent.tagName === "STRONG" ||
      parent.style.fontWeight === "bold" ||
      parent.style.fontWeight === "700"
    ) {
      return true;
    }
    parent = parent.parentElement;
  }
  return false;
}

// ---- 组件 ----

export default function BlockEditModal({
  block,
  resumeId,
  onClose,
}: BlockEditModalProps) {
  const dispatch = useResumeDispatch();

  // 个人信息状态
  const [name, setName] = useState(block.personalInfo?.name ?? "");
  const [phone, setPhone] = useState(block.personalInfo?.phone ?? "");
  const [email, setEmail] = useState(block.personalInfo?.email ?? "");
  const [location, setLocation] = useState(block.personalInfo?.location ?? "");
  const [photoUrl, setPhotoUrl] = useState(block.personalInfo?.photoUrl ?? null);
  const [uploading, setUploading] = useState(false);

  // 正文状态
  const [category, setCategory] = useState<ContentCategory>(
    block.content?.category ?? "项目经历"
  );
  const [timeSpan, setTimeSpan] = useState(block.content?.timeSpan ?? "");
  const [bulletPoints, setBulletPoints] = useState(
    block.content?.bulletPoints ?? false
  );

  const editorRef = useRef<HTMLDivElement>(null);

  // 初始化 contentEditable 内容
  const initialHtml = block.content ? spansToHtml(block.content.spans) : "";

  // 加粗：使用 execCommand
  const handleBold = useCallback(() => {
    document.execCommand("bold", false);
    editorRef.current?.focus();
  }, []);

  // 插入圆点
  const handleInsertBullet = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    const bulletNode = document.createTextNode("• ");
    range.insertNode(bulletNode);
    // 光标移到插入内容之后
    range.setStartAfter(bulletNode);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    editorRef.current?.focus();
  }, []);

  // 上传照片
  async function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!["image/jpeg", "image/png", "image/jpg"].includes(file.type)) {
      alert("仅支持 JPG/PNG 格式");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("文件大小不能超过 5MB");
      return;
    }

    setUploading(true);
    try {
      const result = await api.uploadPhoto(resumeId, file);
      setPhotoUrl(result.photoUrl);
    } catch (err) {
      console.error("照片上传失败:", err);
      alert("照片上传失败");
    } finally {
      setUploading(false);
    }
  }

  function handleSave() {
    let updated: Block;

    if (block.type === "personal_info") {
      updated = {
        ...block,
        personalInfo: {
          name,
          phone,
          email,
          location,
          photoUrl,
        },
      };
    } else {
      const html = editorRef.current?.innerHTML ?? "";
      updated = {
        ...block,
        content: {
          category,
          timeSpan: timeSpan.trim(),
          spans: htmlToSpans(html),
          bulletPoints,
        },
      };
    }

    dispatch({ type: "UPDATE_BLOCK", block: updated });
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-white rounded-xl shadow-xl p-6 w-[560px] max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-gray-800 mb-4">
          {block.type === "personal_info" ? "编辑个人信息" : "编辑正文内容"}
        </h3>

        {block.type === "personal_info" ? (
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">姓名</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="请输入姓名"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">手机号</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="请输入手机号"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">邮箱</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="请输入邮箱"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">现居地</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="请输入现居地"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">照片</label>
              {photoUrl && (
                <img
                  src={photoUrl}
                  alt="照片预览"
                  className="w-20 h-20 object-cover rounded-lg border mb-2"
                />
              )}
              <input
                type="file"
                accept="image/jpeg,image/png"
                onChange={handlePhotoChange}
                disabled={uploading}
                className="text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100 cursor-pointer"
              />
              {uploading && (
                <span className="text-xs text-blue-500 ml-2">上传中...</span>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-sm text-gray-600 mb-1">
                  模块类别
                </label>
                <select
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400 bg-white"
                  value={category}
                  onChange={(e) => setCategory(e.target.value as ContentCategory)}
                >
                  <option value="项目经历">项目经历</option>
                  <option value="实习经历">实习经历</option>
                  <option value="教育经历">教育经历</option>
                  <option value="专业技能">专业技能</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">
                  时间跨度
                </label>
                <input
                  className="w-40 border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400"
                  value={timeSpan}
                  onChange={(e) => setTimeSpan(e.target.value)}
                  placeholder="如 2020.09 - 2024.06"
                />
              </div>
            </div>

            {/* 格式工具栏 */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-3 py-1 text-sm font-bold border border-gray-300 rounded hover:bg-gray-100 transition"
                onMouseDown={(e) => {
                  e.preventDefault(); // 防止编辑器失焦
                  handleBold();
                }}
                title="选中文字后点击加粗"
              >
                B
              </button>
              <button
                type="button"
                className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 transition"
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleInsertBullet();
                }}
                title="在光标位置插入圆点"
              >
                • 列表
              </button>
              <label className="flex items-center gap-1 text-xs text-gray-600 cursor-pointer ml-2">
                <input
                  type="checkbox"
                  checked={bulletPoints}
                  onChange={(e) => setBulletPoints(e.target.checked)}
                  className="rounded"
                />
                全部圆点列表
              </label>
            </div>

            <div>
              <label className="block text-sm text-gray-600 mb-1">
                正文内容
              </label>
              <div
                ref={editorRef}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400 min-h-[160px] max-h-[300px] overflow-y-auto bg-white"
                contentEditable
                suppressContentEditableWarning
                dangerouslySetInnerHTML={{ __html: initialHtml }}
                onKeyDown={(e) => {
                  // Tab 键插入缩进
                  if (e.key === "Tab") {
                    e.preventDefault();
                    document.execCommand("insertText", false, "  ");
                  }
                }}
              />
              <p className="text-xs text-gray-400 mt-1">
                提示：选中文字后点击 <b>B</b> 加粗（加粗效果直接显示），点击 • 插入圆点
              </p>
            </div>
          </div>
        )}

        {/* 底部按钮 */}
        <div className="flex justify-end gap-2 mt-5 pt-3 border-t border-gray-100">
          <button
            className="px-4 py-2 text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="px-4 py-2 text-sm text-white bg-blue-500 rounded-lg hover:bg-blue-600 transition"
            onClick={handleSave}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
