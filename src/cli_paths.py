"""CLI 命令与运行资产路径统一定义（各模块共享，消除重复常量）。"""
import os

NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"
DREAMINA_CMD = os.path.join("bin", "dreamina.exe") if os.name == "nt" else os.path.join("bin", "dreamina")
PLAYWRIGHT_BROWSERS_DIR = os.path.join(".browsers")
