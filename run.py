import os
import sys
import time
import subprocess

backend = None
frontend = None

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

try:
    print("正在启动后端服务...")
    # 使用 sys.executable 确保使用当前 Python 虚拟环境的解释器
    backend = subprocess.Popen(
        [sys.executable, "-m", "src.api.main"],
        cwd=os.getcwd()
    )
    time.sleep(1)

    print("正在启动前端服务...")
    frontend = subprocess.Popen(
        ["npm.cmd" if os.name == 'nt' else "npm", "run", "dev"],
        cwd=os.path.join(os.getcwd(), "frontend")
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

except KeyboardInterrupt:
    print("\n检测到用户中断指令 (Ctrl+C)...")

finally:
    print("开始清理并退出所有子进程...")
    stop_process(frontend, "前端服务")
    stop_process(backend, "后端服务")
    print("所有服务已安全退出。")