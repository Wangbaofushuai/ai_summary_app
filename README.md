# AI 多功能控制台 (ai_summary_app)

基于 **Streamlit + Python** 的全栈 AI 分析工作台，部署于 Linux (Debian) 服务器，通过公网 Web 界面访问。核心生产管道：

```
知识星球抓取 (zsxq-cli) → AI 摘要生成 → 双引擎配图 (Dreamina / Gemini Imagen)
→ md2wechat 微信排版 → 微信公众号发布 (草稿/预览/群发/定时发布)
```

另含：技术指标合规文档制作（docx）、短视频脚本生成、多模型渠道配置（OpenAI/DeepSeek/火山方舟/魔塔）、Cron 定时任务调度、网络代理配置。

## 🚀 快速开始（一键命令 / 管理面板）

**全新安装：服务器上一条命令直接完成安装并弹出管理面板（KEJILION.SH 风格）：**

```bash
bash <(curl -sL https://raw.githubusercontent.com/Wangbaofushuai/ai_summary_app/main/scripts/installer.sh)
```

- 首次执行：自动克隆代码到 `~/ai_summary_app`（可用 `APP_DIR=/path` 覆盖），清理残留可再原地重装
- 后续执行：自动拉取最新代码，直落管理面板
- 依赖（venv/Node/Playwright/即梦 CLI）在面板首次「启动」时由 start.sh 自动检测安装

**已有项目：本地一条命令进入管理面板：**

```bash
./man
```

一条命令直接弹出管理面板（也可用完整路径 `./scripts/man.sh`）。面板常显**运行状态 + 公网访问地址**，四个操作：

| 操作 | 说明 |
|---|---|
| `1` 启动 | 自动检测并安装依赖（venv/Node/Playwright/即梦 CLI 全局部化），后台拉起服务 |
| `2` 退出 | 安全停止服务（含强制兜底） |
| `3` 卸载 | 删除安装产物（`.venv/`、`node_modules/`、dreamina 二进制），**保留**源码/配置/生成产物 |
| `4` 更新 | `git pull` 拉取远程代码 → 增量检查依赖 → 可选热重启 |

非交互环境（如脚本/CI）用子命令形式：`./man start|stop|update|uninstall|status`。

> **宿主机保护**：所有依赖均安装于项目局部（.venv/node_modules）。仅 Playwright 的**系统级运行库**（`--with-deps`，需 apt/root 权限）会对宿主机产生影响，启动时会在交互面板中**先询问你**，未授权则跳过并给出手动指引。

## ⚙️ 手动启动

```bash
./scripts/start.sh          # 依赖检查 + 启动（服务端入口）
./scripts/start.sh --deps-only   # 只检查/安装依赖，不启动
./scripts/start.sh --force       # 强制重装全部依赖
```

> 浏览器直接访问 `http://<服务器IP>:3000`

## 📁 目录结构

```
ai_summary_app/
├── src/                    # 核心代码
│   ├── app.py              # Streamlit 视图层（UI/对话框）
│   ├── scheduler.py        # Cron 调度 / 定时任务 / 手动任务 worker
│   ├── zsxq_client.py      # 知识星球抓取与附件解析
│   ├── image_engine.py     # 即梦 / Gemini 双引擎生图、长图、图片保底
│   ├── wechat_render.py    # md2wechat 排版 / HTML 后处理 / docx 转换
│   ├── wechat_publisher.py # 微信公众号发布（凭证/上传/草稿/群发）
│   ├── llm.py              # LLM 封装（多渠道 completions / 摘要）
│   ├── prompts.py          # 全部系统提示词（合规体系）
│   ├── config_store.py     # config.json / indicators.json 读写
│   └── logo.png            # UI 资产
├── scripts/                # 启动与管理
│   ├── man.sh              # ⭐ 一键管理面板（根目录 ./man 快捷入口）
│   ├── start.sh            # 依赖检查 + 启动（LF 换行，Linux）
│   ├── start.bat           # Windows 对应脚本
│   ├── pre_commit_guard.py # 启动守卫（AST 拦截 pip/npm 动态改环境）
│   └── requirements.txt    # Python 依赖清单
├── config/                 # 运行配置（git 忽略：含微信凭证）
├── outputs/                # 运行产物（推文/长图/脚本/日志）
├── tests/                  # 本地调试与单元测试（git 忽略）
└── .learnings/             # AI 经验记忆
```

## ✅ 运行自检

```bash
.venv/bin/python scripts/pre_commit_guard.py   # 启动守卫
.venv/bin/python tests/test_core_functions.py  # 16 个核心单测
```

## 🧾 功能模块

- **AI 深度分析**：星球动态/文件 → 合规深度报告（长图下载）→ 公众号推文（配图+排版+发布）
- **视频脚本制作器**：基于历史脚本风格的金融/交易内容脚本续写
- **指标文档制作**：技术指标源码 → 合规化分析文档 + 社群互动手册（Word）
- **公众号管理**：多账号、草稿/预览/群发/定时发布、推文编辑器
- **动态 Cron 配置器**：可视化生成 crontab 表达式 + 未来 5 次执行预演

## 📄 许可证说明

本项目为学习与测试用途，包含外部 CLI（`zsxq-cli` / `md2wechat` / Dreamina CLI）与第三方 AI 服务，请遵循各自服务条款使用。
