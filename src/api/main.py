"""FastAPI 应用入口。"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router, set_llm_client
from src.config.loader import load_providers
from src.llm.factory import create_client


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(title="JobHelper API")

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

    app = create_app()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
