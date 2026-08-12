import os
import sys
import time
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MCP_PORT = "8931"
MCP_USER_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "browser-profile")


def stop_process(proc, name):
    """优雅或强制终止子进程及其派生子进程"""
    if proc and proc.poll() is None:
        print(f"正在关闭 {name} (PID: {proc.pid})...")
        try:
            if os.name == 'nt':
                # Windows 下通过 taskkill 递归终止进程树 (/T) 并强制执行 (/F)
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception as e:
            print(f"关闭 {name} 失败: {e}")


def is_port_in_use(port):
    """检测端口是否已被占用（同时检查 IPv4/IPv6 回环地址）。"""
    import socket
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def main():
    backend = None
    frontend = None
    mcp = None

    try:
        # 1. 启动 Playwright MCP 服务（有头浏览器 + 持久化 profile，供投递表单填写）
        if is_port_in_use(int(MCP_PORT)):
            print(f"检测到端口 {MCP_PORT} 已被占用，跳过 Playwright MCP 启动（若已在运行则直接复用）。")
        else:
            print("正在启动 Playwright MCP 服务...")
            npx = "npx.cmd" if os.name == "nt" else "npx"
            # 固定到已验证的版本 0.0.79：该版本提供 browser_fill_form / browser_file_upload 等工具名，
            # 升级版本前请确认工具名与 src/tools/builtin/browser_*.py 中的调用一致
            mcp = subprocess.Popen(
                [npx, "--yes", "@playwright/mcp@0.0.79",
                 "--port", MCP_PORT,
                 "--user-data-dir", MCP_USER_DATA_DIR],
                cwd=PROJECT_ROOT,
            )
            # 等待 npx 拉取/启动（后端工具为懒连接，即使尚未就绪也不会报错）
            time.sleep(3)

        print("正在启动后端服务...")
        # 使用 sys.executable 确保使用当前 Python 虚拟环境的解释器
        backend = subprocess.Popen(
            [sys.executable, "-m", "src.api.main"],
            cwd=PROJECT_ROOT
        )
        time.sleep(1)

        print("正在启动前端服务...")
        frontend = subprocess.Popen(
            ["npm.cmd" if os.name == 'nt' else "npm", "run", "dev"],
            cwd=os.path.join(PROJECT_ROOT, "frontend")
        )

        print("\n服务启动成功！按 Ctrl+C 可优雅退出所有服务。\n")

        # 循环轮询进程状态
        while True:
            time.sleep(0.5)
            # 检查是否其中某一个进程意外崩溃/退出
            if backend.poll() is not None:
                print("后端服务已意外终止。")
                break
            if frontend.poll() is not None:
                print("前端服务已意外终止。")
                break
            if mcp and mcp.poll() is not None:
                print("Playwright MCP 服务已意外终止。")
                break

    except KeyboardInterrupt:
        print("\n检测到用户中断指令 (Ctrl+C)...")

    finally:
        print("开始清理并退出所有子进程...")
        stop_process(mcp, "Playwright MCP 服务")
        stop_process(frontend, "前端服务")
        stop_process(backend, "后端服务")
        print("所有服务已安全退出。")


if __name__ == "__main__":
    main()
