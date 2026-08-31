#!/bin/bash
# ============================================================
#  AI 多功能控制台 · 在线一键安装/启动器
#  用法（KEJILION.SH 风格单行命令）:
#    bash <(curl -sL https://raw.githubusercontent.com/Wangbaofushuai/ai_summary_app/main/scripts/installer.sh)
#  行为:
#    首次执行  -> 克隆代码到 $HOME/ai_summary_app（默认，可用 APP_DIR 覆盖）
#    后续执行  -> git pull 拉取最新代码（本地有未提交改动则保留本地版本）
#    最后      -> 直接进入交互式管理面板（man.sh）
#  注意: 依赖（venv/node/playwright/即梦 CLI）在面板"1 启动"时由 start.sh 自动检测安装。
# ============================================================
set -e

REPO_URL="https://github.com/Wangbaofushuai/ai_summary_app.git"
APP_DIR="${APP_DIR:-$HOME/ai_summary_app}"

echo "=========================================="
echo "   AI 多功能控制台 · 一键启动器"
echo "=========================================="
echo "   应用目录 : $APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
    echo ""
    echo "[1/2] 首次安装：正在克隆代码仓库..."
    git clone --depth 1 "$REPO_URL" "$APP_DIR"
else
    echo ""
    echo "[1/2] 检测到已有项目：正在拉取最新代码..."
    cd "$APP_DIR"
    if git pull --ff-only origin main 2>/dev/null; then
        echo "       更新成功"
    else
        echo "       ⚠️ 拉取失败（可能有未提交改动），本次保留本地版本继续。"
        echo "       如需更新请检查: git status"
    fi
fi

cd "$APP_DIR"
chmod +x scripts/man.sh
echo "[2/2] 进入管理面板..."
echo ""
exec bash scripts/man.sh
