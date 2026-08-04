"""终端对话应用主控。

启动流程：加载配置 → 选择供应商 → 创建客户端 → 进入对话循环。
"""

import asyncio
import signal
import sys
from pathlib import Path

from src.config.loader import load_providers
from src.llm.factory import create_client
from src.llm.types import Message, ProviderConfig, TextChunk, ThinkingChunk


# ---- ANSI 终端样式 ----
_DIM = "\033[2m"
_GRAY = "\033[90m"
_RESET = "\033[0m"


def _dim(text: str) -> str:
    """灰显文本。"""
    return f"{_GRAY}{text}{_RESET}"


def _faint(text: str) -> str:
    """弱化文本。"""
    return f"{_DIM}{text}{_RESET}"


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


def select_provider(providers: list[ProviderConfig]) -> ProviderConfig:
    """终端交互：选择供应商。单供应商直接返回。"""
    if len(providers) == 1:
        p = providers[0]
        print(f"使用唯一供应商: {p.name} ({p.protocol}, {p.model})")
        return p

    print("\n可用供应商:")
    for i, p in enumerate(providers, 1):
        thinking_label = " [thinking]" if p.thinking else ""
        print(f"  {i}. {p.name} ({p.protocol} / {p.model}){thinking_label}")

    while True:
        try:
            raw = input(f"\n请选择 (1-{len(providers)}): ").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(providers):
                chosen = providers[idx]
                print(f"已选择: {chosen.name}")
                return chosen
            print(f"请输入 1-{len(providers)} 之间的数字")
        except ValueError:
            print("请输入有效数字")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            sys.exit(0)


async def ainput(prompt: str = "") -> str:
    """异步版 input()。"""
    return await asyncio.to_thread(input, prompt)


async def chat_loop(client, provider: ProviderConfig) -> None:
    """多轮对话循环。"""
    messages: list[Message] = []
    client_display = f"{provider.name}/{provider.model}"

    print(f"\n===== JobHelper 对话 Demo ({client_display}) =====")
    print("输入 /quit 退出，Ctrl+C 也可退出")
    print("=" * 40)

    while True:
        try:
            user_input = await ainput("\nUser > ")
        except (EOFError, KeyboardInterrupt):
            print("\n\n再见！")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("再见！")
            break

        # 追加用户消息
        messages.append(Message(role="user", content=user_input))

        # 流式输出 LLM 回复
        print()
        full_response: list[str] = []
        thinking_active = False

        try:
            async for event in client.stream(messages):
                if isinstance(event, ThinkingChunk):
                    if not thinking_active:
                        thinking_active = True
                        print(f"  {_dim('[思考]')} ", end="", flush=True)
                    print(_faint(event.delta), end="", flush=True)

                elif isinstance(event, TextChunk):
                    if thinking_active:
                        thinking_active = False
                        print()
                        print(f"  {_dim('[思考结束]')}")
                        print(f"Assistant > ", end="", flush=True)

                    elif not full_response:
                        print(f"Assistant > ", end="", flush=True)

                    print(event.delta, end="", flush=True)
                    full_response.append(event.delta)

        except Exception as e:
            print(f"\n  [调用错误: {e}]")
            messages.pop()
            continue

        print()  # 最终换行

        # 追加助手回复到历史
        if full_response:
            messages.append(
                Message(role="assistant", content="".join(full_response))
            )
        else:
            messages.append(Message(role="assistant", content="[空回复]"))


def _on_sigint(signum, frame):
    """Ctrl+C 信号处理器。"""
    print("\n\n再见！")
    sys.exit(0)


async def main() -> None:
    """应用主入口。"""
    signal.signal(signal.SIGINT, _on_sigint)

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

    try:
        provider = select_provider(providers)
    except (KeyboardInterrupt, EOFError):
        print("\n已取消")
        sys.exit(0)

    client = create_client(provider)
    await chat_loop(client, provider)


if __name__ == "__main__":
    asyncio.run(main())
