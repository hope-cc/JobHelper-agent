"""应用日志模块。

统一的日志记录器，覆盖工具调用、LLM 交互、图执行等关键环节。
所有日志输出到 log/app.log，按大小自动轮转。
"""

import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---- 常量 ----
LOG_DIR = Path(__file__).resolve().parent.parent / "log"
LOG_FILE = LOG_DIR / "app.log"
MAX_BYTES = 5 * 1024 * 1024  # 单个日志文件最大 5MB
BACKUP_COUNT = 7              # 保留最近 7 个轮转文件
DATE_FMT = "%Y-%m-%d %H:%M:%S"
LOG_FMT = "[%(asctime)s] [%(levelname)s] %(message)s"

# ---- 确保目录 ----
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---- 共享 Logger ----
_logger = logging.getLogger("jobhelper")
_logger.setLevel(logging.DEBUG)

if not _logger.handlers:
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
    _logger.addHandler(handler)


# ---- 便捷函数 ----

def tool_call_start(tool_name: str, tool_id: str, arguments_preview: str = "") -> None:
    """记录工具调用开始。"""
    msg = f"[TOOL] [CALL-START] tool={tool_name} id={tool_id}"
    if arguments_preview:
        msg += f" args={arguments_preview[:200]}"
    _logger.info(msg)


def tool_call_result(tool_name: str, tool_id: str, output: str, is_error: bool) -> None:
    """记录工具执行结果。"""
    status = "ERROR" if is_error else "OK"
    preview = output[:300].replace("\n", "\\n")
    _logger.info(f"[TOOL] [CALL-RESULT] tool={tool_name} id={tool_id} status={status} output={preview}")


def llm_request_start(model: str, msg_count: int, tool_count: int) -> str:
    """记录 LLM 请求开始，返回 request_id 用于后续关联。"""
    rid = datetime.now().strftime("%H%M%S%f")[:12]
    _logger.info(f"[LLM] [REQ-START] rid={rid} model={model} messages={msg_count} tools={tool_count}")
    return rid


def llm_request_done(rid: str, text_len: int, tool_calls_count: int) -> None:
    """记录 LLM 请求完成。"""
    _logger.info(f"[LLM] [REQ-DONE] rid={rid} text_chars={text_len} tool_calls={tool_calls_count}")


def llm_request_error(rid: str, error: str) -> None:
    """记录 LLM 请求出错。"""
    _logger.error(f"[LLM] [REQ-ERROR] rid={rid} error={error}")


def graph_loop(loop: int, msg_count: int, tool_count: int, text_chars: int, tool_calls: int) -> None:
    """记录 ReAct 循环结束。"""
    _logger.info(
        f"[GRAPH] [LOOP] round={loop} messages={msg_count} tools_available={tool_count} "
        f"text_chars={text_chars} tool_calls={tool_calls}"
    )


def tool_exec(tool_name: str, tool_id: str, elapsed_ms: int, is_error: bool) -> None:
    """记录图中单个工具执行。"""
    status = "ERROR" if is_error else "OK"
    _logger.info(f"[GRAPH] [TOOL-EXEC] tool={tool_name} id={tool_id} elapsed={elapsed_ms}ms status={status}")


def api_request(conversation_id: str, msg_len: int) -> str:
    """记录 API 请求开始，返回 request_id。"""
    rid = datetime.now().strftime("%H%M%S%f")[:12]
    _logger.info(f"[API] [REQ-START] rid={rid} conv={conversation_id} msg_len={msg_len}")
    return rid


def api_request_done(rid: str, response_len: int, tool_calls_count: int) -> None:
    """记录 API 请求完成。"""
    _logger.info(f"[API] [REQ-DONE] rid={rid} response_chars={response_len} tool_calls={tool_calls_count}")


def api_request_error(rid: str, error: str) -> None:
    """记录 API 请求出错。"""
    _logger.error(f"[API] [REQ-ERROR] rid={rid} error={error}")

def sub_agent_info(rid: str, state:str) -> None:
    """记录子 agent 执行状态。"""
    _logger.info(f"[SUB-AGENT] [STATE] rid={rid} state={state}")
