#!/bin/bash

FORCE_INSTALL=0
if [ "$1" == "--force" ]; then
    FORCE_INSTALL=1
    echo "[FORCE] Force reinstall of all dependencies requested."
fi

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

echo "Checking and linking skills directory to .agents/skills..."
if [ ! -d ".agents" ]; then
    mkdir .agents
fi
if [ ! -d ".agents/skills" ] && [ ! -L ".agents/skills" ]; then
    echo "Creating Symbolic Link: .agents/skills -> skills"
    ln -s ../skills .agents/skills
fi

echo "Running pre-commit guard..."
python3 pre_commit_guard.py
if [ $? -ne 0 ]; then
    echo "[ERROR] Pre-commit guard failed. Aborting startup."
    exit 1
fi

echo "Installing Dreamina CLI..."
if [ ! -f "dreamina" ]; then
    curl -fsSL -o dreamina "https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_linux_amd64"
    chmod +x dreamina
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
        uv pip install -r requirements.txt
    else
        pip install -r requirements.txt
    fi
    if [ $? -eq 0 ]; then
        echo "done" > .venv/.pip_install_done
    fi
else
    echo "Python dependencies already installed. Skipping."
fi

echo "正在检查 Playwright 浏览器依赖..."
if [ ! -f ".venv/.playwright_install_done" ] || [ "$FORCE_INSTALL" -eq 1 ]; then
    echo "正在安装 Playwright 浏览器依赖..."
    playwright install chromium --with-deps
    if [ $? -eq 0 ]; then
        echo "done" > .venv/.playwright_install_done
    fi
else
    echo "Playwright browser already installed. Skipping."
fi

echo "启动 Streamlit 网页服务..."
streamlit run app.py --server.port 3000 --server.address 0.0.0.0