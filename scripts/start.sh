#!/bin/bash

# 切换到项目根目录（脚本位于 scripts/ 下），保证后续相对路径语义不变
cd "$(dirname "$0")/.."

# Playwright 浏览器库存入项目内（不污染宿主机 ~/.cache）
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.browsers"
mkdir -p .browsers
# 运行数据目录（新机器 clone 后不存在）
mkdir -p config outputs

# 服务端口：可由环境变量 PORT 或 --port <num> 覆盖（默认 3100，避开宿主其他服务）
PORT="${PORT:-3100}"
FORCE_INSTALL=0
DEPS_ONLY=0
ALLOW_SYSDEPS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --force) FORCE_INSTALL=1; echo "[FORCE] Force reinstall of all dependencies requested."; shift;;
        --deps-only) DEPS_ONLY=1; shift;;
        --allow-sysdeps) ALLOW_SYSDEPS=1; shift;;
        --port) PORT="$2"; shift 2;;
        *) echo "[WARN] 未知参数: $1"; shift;;
    esac
done

# 人机确认辅助：是否为交互终端
is_tty() { [ -t 0 ] && [ -t 1 ]; }

echo "正在检查和初始化 Python 虚拟环境..."
if [ ! -d ".venv" ]; then
    if command -v uv &> /dev/null; then
        echo "检测到 uv，使用 uv venv 创建虚拟环境..."
        uv venv
    else
        echo "未检测到 uv，降级使用 python3 -m venv 创建虚拟环境..."
        python3 -m venv .venv
    fi
    FORCE_INSTALL=1
fi
source .venv/bin/activate

echo "Running pre-commit guard..."
python3 scripts/pre_commit_guard.py
if [ $? -ne 0 ]; then
    echo "[ERROR] Pre-commit guard failed. Aborting startup."
    exit 1
fi

echo "Installing Dreamina CLI..."
if [ ! -f "bin/dreamina" ]; then
    mkdir -p bin && curl -fsSL -o bin/dreamina "https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_linux_amd64"
    chmod +x bin/dreamina
fi

echo "正在检查 Node 依赖..."
if [ ! -d "node_modules" ] || [ "$FORCE_INSTALL" -eq 1 ]; then
    echo "正在局部安装 Node 依赖..."
    npm install zsxq-cli
else
    echo "Node dependencies already installed. Skipping."
fi

echo "正在检查 Python 依赖..."
if [ ! -f ".venv/.pip_install_done" ] || [ "$FORCE_INSTALL" -eq 1 ]; then
    echo "正在安装 Python 依赖..."
    if command -v uv &> /dev/null; then
        uv pip install -r scripts/requirements.txt
    else
        pip install -r scripts/requirements.txt
    fi
    if [ $? -eq 0 ]; then
        echo "done" > .venv/.pip_install_done
    fi
else
    echo "Python dependencies already installed. Skipping."
fi

echo "正在检查 Playwright 浏览器依赖..."
if [ ! -f ".venv/.playwright_install_done" ] || [ "$FORCE_INSTALL" -eq 1 ]; then
    echo "正在安装 Playwright 浏览器依赖 (本地缓存目录...)"
    playwright install chromium
    if [ $? -ne 0 ]; then
        echo "[ERROR] Playwright chromium 安装失败，Aborting."
        exit 1
    fi
    # 系统级依赖（--with-deps 需要 apt 等系统库，属宿主机影响），默认征求用户确认
    echo ""
    echo "[宿主影响提醒] 完整运行 Playwright 通常还需要一部分【系统级运行库】。"
    echo "  安装方式: playwright install chromium --with-deps (需要 root/apt 权限，属于对宿主机环境的修改)"
    if [ "$ALLOW_SYSDEPS" -eq 1 ]; then
        echo "[--allow-sysdeps] 已放行，正在安装系统级依赖..."
        playwright install chromium --with-deps
    elif is_tty; then
        echo -n "是否现在安装系统级依赖? (y/N): "
        read -r ans
        case "$ans" in
            y|Y|yes|YES)
                echo "正在安装系统级依赖..."
                playwright install chromium --with-deps
                ;;
            *)
                echo "已跳过系统级依赖安装。若后续浏览器报错，请手动执行:"
                echo "  source .venv/bin/activate && playwright install chromium --with-deps"
                ;;
        esac
    else
        echo "非交互环境，默认跳过。需要时请执行: playwright install chromium --with-deps"
    fi
    if [ $? -eq 0 ]; then
        echo "done" > .venv/.playwright_install_done
    fi
else
    echo "Playwright browser already installed. Skipping."
fi

if [ "$DEPS_ONLY" -eq 1 ]; then
    echo "[deps-only] 依赖检查完成，退出（不启动服务）。"
    exit 0
fi

echo "启动 Streamlit 网页服务..."
echo "访问地址: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}"
streamlit run src/app.py --server.port "$PORT" --server.address 0.0.0.0
