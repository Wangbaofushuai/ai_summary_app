#!/bin/bash

# ============================================================
#  AI 多功能控制台 · 一键管理面板 (man.sh)
#  用法:
#    ./scripts/man.sh              # 交互式管理面板（推荐，SSH/终端下使用）
#    ./scripts/man.sh <命令>       # 非交互子命令: start|stop|update|uninstall|status
# ============================================================

cd "$(dirname "$0")/.."

APP_PATTERN="streamlit run src/app.py"
PORT="${PORT:-3100}"
PANEL_LOG="outputs/man_panel.log"

# ---------------- 信息辅助 ----------------
is_running() { pgrep -f "$APP_PATTERN" >/dev/null 2>&1; }

get_public_ip() {
    # 实时读取主机网卡 IP（跟随机器变化），过滤回环/容器内网网段
    local ip
    ip=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|10\.|192\.168\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[01]\.)' | head -1)
    # 容器网卡也可能是唯一地址，放宽取第一个非回环地址
    if [ -z "$ip" ]; then
        ip=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^127\.' | head -1)
    fi
    # 全部失败时用公网出口 IP 兜底
    if [ -z "$ip" ]; then
        ip=$(curl -s --max-time 3 https://api.ipify.org 2>/dev/null)
    fi
    [ -n "$ip" ] && echo "$ip" && return
    echo "127.0.0.1"
}

panel_info() {
    echo "==============================="
    echo "   AI 多功能控制台 · 管理面板"
    echo "==============================="
    if is_running; then
        echo "   运行状态 : ✅ 运行中 (PID: $(pgrep -f "$APP_PATTERN" | head -1))"
    else
        echo "   运行状态 : ⛔ 已停止"
    fi
    IP=$(get_public_ip)
    [ -n "$IP" ] && echo "   访问地址 : http://${IP}:${PORT}" || echo "   访问地址 : 无法获取外网 IP，请尝试本机 http://127.0.0.1:${PORT}"
    echo "==============================="
}

# ---------------- 生命周期动作 ----------------
do_start() {
    if is_running; then
        echo "⚠️  服务已在运行中，无需重复启动。"
        return 0
    fi
    echo "🚀 正在启动服务（首次安装/更新依赖可能需要数分钟，期间自动显示安装日志）..."
    nohup ./scripts/start.sh >> "$PANEL_LOG" 2>&1 &
    detect_pid=$!
    elapsed=0
    while [ $elapsed -lt 480 ]; do
        if is_running; then
            sleep 2
            echo "✅ 启动成功"
            panel_info
            echo "📄 完整日志: outputs/man_panel.log"
            return 0
        fi
        if ! kill -0 $detect_pid 2>/dev/null; then
            echo "❌ 启动进程已退出（依赖安装失败），日志末尾如下:"
            tail -25 "$PANEL_LOG"
            return 1
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        if [ $((elapsed % 20)) -eq 0 ]; then
            echo ""
            echo "⏳ 安装/启动进行中 (${elapsed}s)... 最近日志:"
            tail -4 "$PANEL_LOG" 2>/dev/null
        fi
    done
    echo "❌ 启动超时（480 秒），日志末尾如下:"
    tail -25 "$PANEL_LOG"
    return 1
}

do_stop() {
    if ! is_running; then
        echo "⚠️  服务当前未在运行。"
        return 0
    fi
    echo "🛑 正在停止服务..."
    pkill -f "$APP_PATTERN"
    sleep 2
    if is_running; then
        pkill -9 -f "$APP_PATTERN" 2>/dev/null
        sleep 1
    fi
    if is_running; then
        echo "❌ 未能完全停止，请手动检查进程: pgrep -af streamlit"
        return 1
    fi
    echo "✅ 服务已停止"
    return 0
}

is_tty() { [ -t 0 ] && [ -t 1 ]; }

do_update() {
    echo "🔄 正在从远程仓库更新代码..."
    if git pull --ff-only origin main 2>&1; then
        echo "✅ 代码更新完成"
        echo "→ 检查并安装新增依赖（不启动服务）..."
        ./scripts/start.sh --deps-only
        if is_running; then
            if is_tty; then
                echo "ℹ️  服务正在运行中，旧代码需重启生效。"
                echo -n "是否立即重启服务? (y/N): "
                read -r ans
                case "$ans" in
                    y|Y|yes|YES) do_stop && do_start;;
                    *) echo "已保留运行中的旧实例，稍后可手动执行 1) 启动 完成重启。";;
                esac
            else
                echo "ℹ️  服务正在运行中（非交互环境），请稍后执行: ./man restart"
            fi
        fi
    else
        echo "❌ 更新失败（可能本地有未提交改动），请检查 git status。"
    fi
}

do_uninstall() {
    if ! is_running; then
        echo "ℹ️  服务未运行。"
    else
        echo "⚠️  服务正在运行，卸载前需停止。"
        do_stop
    fi
    echo "以下将删除【安装产物】（不影响 config/ 数据配置与 outputs/ 生成文件）:"
    echo "   - .venv/        Python 虚拟环境"
    echo "   - node_modules/ Node 依赖"
    echo "   - bin/          即梦 CLI 等运行时二进制"
    echo "   - outputs/ 运行日志与占位文件"
    echo -n "⚠️  确认卸载? (y/N): "
    read -r ans
    case "$ans" in
        y|Y|yes|YES)
            rm -rf .venv node_modules bin
            rm -f outputs/man_panel.log outputs/cron_execution.log outputs/manual_execution.log outputs/manual_task_state.json
            echo "✅ 卸载完成。已保留 AGENTS.md 源码、src/ 代码、config/ 配置与 outputs/ 生成产物。"
            ;;
        *) echo "❎ 已取消卸载。";;
    esac
}

do_status() {
    if is_running; then
        panel_info
        echo "进程详情 :"
        pgrep -af "$APP_PATTERN" || true
        echo "日志输出 : outputs/man_panel.log (最近 5 行)"
        tail -5 "$PANEL_LOG" 2>/dev/null || echo "            (暂无)"
    else
        panel_info
    fi
}

do_restart() {
    do_stop
    sleep 1
    do_start
}

do_clean() {
    echo "🧹 当前运行产物占用:"
    du -sh outputs 2>/dev/null || echo "   (outputs 不存在)"
    files=$(find outputs -type f 2>/dev/null | wc -l)
    echo "   待清理文件数: ${files}"
    if [ "$files" -eq 0 ]; then
        echo "ℹ️  outputs 已是空目录，无需清理。"
        return 0
    fi
    echo -n "⚠️  确认清空 outputs/（推文/配图/长图/脚本/日志全部删除，目录保留）? (y/N): "
    if is_tty; then
        read -r ans
    else
        ans="N"
        echo "(非交互环境默认不清理)"
    fi
    case "$ans" in
        y|Y|yes|YES)
            find outputs -type f -delete
            mkdir -p outputs/wechat/images outputs/images outputs/scripts outputs/indicator_docs
            echo "✅ 清理完成（目录骨架已保留）"
            ;;
        *) echo "❎ 已取消清理。";;
    esac
}

# ---------------- 主循环 ----------------
interactive_loop() {
    while true; do
        clear
        panel_info
        echo "   1) 启动服务          2) 停止服务"
        echo "   3) 重启服务          4) 更新代码与依赖"
        echo "   5) 卸载安装产物      6) 清理历史产物"
        echo ""
        echo "   0) 退出面板"
        echo ""
        echo -n "  请选择操作 [0-6]: "
        read -r choice
        case "$choice" in
            1) do_start;;
            2) do_stop;;
            3) do_restart;;
            4) do_update;;
            5) do_uninstall;;
            6) do_clean;;
            0) echo "👋 再见"; exit 0;;
            *) echo "未识别的选项: $choice";;
        esac
        echo ""
        echo -n "按回车键继续..."
        read -r dummy
    done
}

# ---------------- 入口 ----------------
mkdir -p outputs
if [ $# -eq 0 ]; then
    interactive_loop
else
    # 非交互子命令模式：man.sh start|stop|update|uninstall|status
    case "$1" in
        start)   do_start;;
        stop)    do_stop;;
        restart) do_restart;;
        update)  do_update;;
        uninstall) do_uninstall;;
        clean)   do_clean;;
        status)  do_status;;
        *) echo "用法: ./man [start|stop|restart|update|uninstall|clean|status] | (无参数进入管理面板)"; exit 1;;
    esac
fi
