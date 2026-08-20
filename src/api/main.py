"""FastAPI 应用入口。"""

import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router, set_llm_client, set_registry
from src.config.loader import load_providers, load_app_settings
from src.llm.factory import create_client
from src.tools.registry import ToolRegistry


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    # 应用退出时关闭 Playwright MCP 持久会话，避免事件循环退出时告警
    try:
        from src.browser_mcp.client import close as close_mcp_client
        await close_mcp_client()
    except Exception:
        pass


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(title="JobHelper API", lifespan=_lifespan)

    # CORS —— 允许前端开发服务器访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


logger = logging.getLogger(__name__)





def _find_config() -> str:
    """查找配置文件，当前目录优先。"""
    candidates = [
        "config.yaml",
        "config.yml",
        str(Path(__file__).resolve().parent.parent.parent / "config.yaml"),
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return "config.yaml"


def main():
    """启动 API 服务。"""
    config_path = _find_config()
    try:
        providers = load_providers(config_path)
    except FileNotFoundError:
        print(f"错误: 配置文件不存在: {config_path}")
        print("请参考 config.example.yaml 创建 config.yaml")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 配置文件读取失败: {e}")
        sys.exit(1)

    if not providers:
        print("错误: 未配置任何 LLM 供应商")
        sys.exit(1)

    # 使用第一个供应商（单供应商配置）
    provider = providers[0]
    print(f"使用供应商: {provider.name} ({provider.protocol}, {provider.model})")

    client = create_client(provider)
    set_llm_client(client)

    # 初始化工具注册中心
    registry = ToolRegistry.get_instance()
    registry.discover("src.tools.builtin")
    tool_count = len(registry.list_definitions())
    if tool_count > 0:
        print(f"已加载 {tool_count} 个工具: {[d['name'] for d in registry.list_definitions()]}")
    else:
        print("提示: 未发现任何工具（在 src/tools/builtin/ 下创建工具文件即可自动发现）")
    set_registry(registry)

    # 注入子 agent worker_fn（mock 实现，后续替换为真实实现）
    from src.tools.builtin.dispatch_tasks import task_dispatcher
    settings = load_app_settings(config_path)
    max_concurrency = settings.get("max_concurrency", 3)
    task_dispatcher.set_provider_config(provider)
    task_dispatcher.set_worker_num(max_concurrency)

    # 注入招聘信息向量库配置（缺省用默认值，不配置也能跑）
    from src.rag.store import job_vector_store
    rag_cfg = settings.get("rag", {}) or {}
    job_vector_store.configure(
        ollama_base_url=rag_cfg.get("ollama_base_url"),
        embedding_model=rag_cfg.get("embedding_model"),
        vector_dir=rag_cfg.get("vector_dir"),
        retrieval_top_k=rag_cfg.get("retrieval_top_k"),
    )

    # 自动拉起 Playwright MCP 服务（后台线程启动，不阻塞后端/前端访问；
    # 客户端在首次调用时若连不上会短时重试）
    # mcp_handle = McpServerHandle()
    # if settings.get("playwright_mcp_auto_start", True):
    #     mcp_url = settings.get("playwright_mcp_url", DEFAULT_MCP_URL)
    #     mcp_user_dir = settings.get("playwright_mcp_user_data_dir") or None
    #     mcp_wait = float(settings.get("playwright_mcp_startup_wait", 120))
    #     threading.Thread(
    #         target=_start_mcp_in_background,
    #         args=(mcp_handle, mcp_url, mcp_user_dir, mcp_wait),
    #         name="mcp-server-start",
    #         daemon=True,
    #     ).start()
    # else:
    #     print(
    #         "Playwright MCP 服务自动启动已禁用（如需启用，请在 config.yaml 的"
    #         "settings.playwright_mcp_auto_start 设为 true）"
    #     )

    app = create_app()

    import uvicorn

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        # mcp_handle.stop_sync()
        pass


if __name__ == "__main__":
    main()
