#!/bin/bash
echo "正在检查和初始化 Python 虚拟环境..."
if [ ! -d ".venv" ]; then
    if command -v uv &> /dev/null; then
        echo "检测到 uv，使用 uv venv 创建虚拟环境..."
        uv venv
    else
        echo "未检测到 uv，降级使用 python3 -m venv 创建虚拟环境..."
        python3 -m venv .venv
    fi
fi
source .venv/bin/activate

echo "Running pre-commit guard..."
python3 pre_commit_guard.py
if [ $? -ne 0 ]; then
    echo "[ERROR] Pre-commit guard failed. Aborting startup."
    exit 1
fi


echo "正在局部安装 Node 依赖..."
npm install zsxq-cli

echo "正在安装 Python 依赖..."
uv pip install -r requirements.txt

echo "正在安装 Playwright 浏览器依赖..."
playwright install chromium --with-deps

echo "启动 Streamlit 网页服务..."
streamlit run app.py --server.port 3000 --server.address 0.0.0.0