# 🤖 AI 架构师开发手册

> **最高指导原则**：版本迭代、Bug 修复与新功能开发中，所有参与维护的 AI 必须绝对遵守本手册纪律，防止代码冲突与环境污染。

## 1. 项目身份与环境
* **核心架构**：Python 核心逻辑 + Streamlit Web 界面 + Playwright 渲染 + Node CLI 工具（`zsxq-cli`、`md2wechat`）。
* **当前环境**：Linux (Debian) 服务器部署，AI 经公网 IP + Web 界面交互，代码变更**直接落盘服务器项目根目录**（唯二例外：下载 CLI 二进制、容器外调用 SDK）。
* **用途**：学习与测试为主，安全要求宽松，但「不污染宿主机」是不可放弃的底线。

## 2. DevOps 工作模式
* **服务器为唯一工作环境**：无「Windows 本地 + WinSCP 单向同步」拓扑；若重新引入双端同步模式必须先更新本手册。
* **防逆向污染**：外部历史环境（旧 Windows 本地机、旧远端仓库）严禁作为权威内容回灌本目录；**服务器项目目录是唯一代码真理源**。
* **双端源码红线不变**：`sys.platform` 分支、`start.bat`/`start.sh` 成对维护，不允许出现仅单平台可用的代码。

## 3. 绿色的“沙箱隔离”原则
* **彻底的局部环境**：锁定 `.venv`。严禁修改宿主机全局环境变量，严禁全局命令（`npm install -g`、全局 `pip install`、`apt install` 等）。
* **依赖管理**：推荐 `uv`（`uv venv` / `uv pip install`）；`node_modules`、`.venv`、`__pycache__`、`tests` 应列入文件同步黑名单。
* **宿主机零污染**：安装/写入/缓存/进程默认限定在项目根目录内；凡触及根目录以外（`systemctl`、`crontab`、`apt`、全局 npm、`/etc/`、`/root/` 其他目录、非项目端口等），必须先向用户说明影响面并**等待用户决定**；已产生冗余系统影响，任务结束前回滚或汇报。

## 4. 启动与测试规范
严禁使用 `python app.py` 作为启动命令，必须走沙箱入口：
* **本地测试 (Windows)**：`.\scripts\start.bat`
* **远程部署 (Debian)**：`./scripts/start.sh`
* 两脚本内含 cd 回项目根的目录自适应逻辑，保证进程 cwd=项目根（app.py 的 `config/`、`outputs/`、`./dreamina` 均按 cwd 相对定位）。

## 5. 项目文件结构纪律与目录整洁规范
* **根目录白名单**：`AGENTS.md`、`package.json`/`package-lock.json`（Node 三件套与 `node_modules/` 同居根目录，npx 解析硬约束）、`.gitignore`/`.gitattributes` 及职能子目录（`.venv/`、`node_modules/`、`outputs/`、`tests/`、`.learnings/`、`config/`、`scripts/`、`src/`）；**禁止任何 py/js 来源文件散落根目录**。
* **归属约定**：核心代码入 `src/`（含 `logo.png`）；启动/守卫脚本入 `scripts/`；运行配置入 `config/`（已被 `.gitignore` 忽略）；Python 依赖清单收于 `scripts/requirements.txt`。
* **测试隔离**：测试/调试文件一律放 `tests/`；运行产物一律放 `outputs/`；严禁在根目录散落临时文件（如 `cat.jpg`、`test.py`、`stderr.txt`）。
* **任务前后双清**：任务开始前审视根目录；任务结束时清理临时中间文件（或归入 `tests/`）、幽灵进程、临时端口、未清理缓存。
* **目录结构同步**：增减/重构模块后**必须先**将最新结构与职责说明更新到本手册「12. 项目目录结构与职责说明」章节，再动手其他工作。

## 6. AI 架构师强制思维纪律
* **先审慎思考再作答**：回答/改码/设计前先深度拆解、逻辑推演、可行性分析（当前**未挂载任何 MCP 服务器**，不依赖外部思考工具，独立推演），确认无合规风险与架构冲突后再输出。
* **任务启动前外部资源盘点**：盘点当前可用资源——① 会话实际挂载的 MCP（目前无）；② 局部 CLI（`zsxq-cli`、`md2wechat`、`dreamina`）与 Playwright；③ `.learnings/` 记忆。判断匹配度后在合适时机调用，禁止装而不用或遗忘。
* **记忆协议诚实执行**：严格履行第 10 章启动加载/结束沉淀协议。

## 7. 跨平台兼容级红线（Linux & Windows 双端强制）
* **核心原则**：任何新功能/依赖引入必须 Windows + Debian 双平台可用。
* **双端实践**：CLI 双路径（`.exe` 后缀判断）、`start.bat`/`start.sh` 成对更新。
* **路径铁律**：所有路径拼接**必须**用 `pathlib.Path` 或 `os.path.join()`，严禁硬编码 `/` 或 `\`。
* **不兼容告知义务**：某操作仅单平台可用时，必须先告知①操作内容②不兼容原因③另一端影响④替代方案，严禁静默执行。

## 8. 变更合规（非 trivial 变更先过方案确认）
* 任何非 trivial 的功能新增、架构变更、Bug 修复，必须先输出**中文方案**（目标/逻辑构思/任务清单/影响面/验证方式），**经用户确认后才可动手**。
* 执行过程中用 checklist 跟踪进度；完成后简要总结变更与验证结果。简易改动（文案、配置、清理）可酌情预先自我评估后实施。

## 9. 防退化与主动沟通规范
* **副作用评估**：改动前思考复用者，警惕在 Streamlit 主渲染链路中引入阻塞调用（如让全局卡顿的 subprocess）。
* **主动提问**：需求模糊、发现隐患、有更好的重构方向时，必须先说清再动手。
* **失败兜底（Fallback）**：外部 API / CLI 假定高失败率；容易失败的环节必须 try-catch + 兜底（如生图失败渲染本地占位图并提示，绝不让管道崩溃或空白）。
* **任务结束清理**：回收临时文件、幽灵进程、临时端口、缓存，不留痕迹。

## 10. 技能与记忆机制
* **技能库现状**：`skills/`、`.agents/` 技能目录与 `.skillhub/` CLI 均已删除（仅服务 AI 辅助开发，程序零引用），本项目不再维护技能体系。
* **智能体记忆协议（纯文件读写）**：
  * **启动时**：①读 `.learnings/LEARNINGS.md`；②读 `.learnings/ERRORS.md`；③涉及已有实体/配置时核对 `config/config.json`。
  * **结束时**：①提取长期复用事实；②经验教训追加 `.learnings/LEARNINGS.md`、错误细节追加 `.learnings/ERRORS.md`；③配置/偏好变更同步 `config.json` 说明。

## 11. 规则手册唯一文件机制（Single File）
* `AGENTS.md` 是项目**唯一 AI 开发规则文件**（历史多平台副本与主源已废除删除）。
* 直接修改 `AGENTS.md`，无任何副本同步。
* 受版本管理保护，禁止静默删除或弱化。

## 12. 项目目录结构与职责说明

本项目采用结构化与模块化设计，各核心文件及目录职责如下：

### 核心代码与业务逻辑（src/ 模块目录）
* **[src/app.py](file:///f:/Jack/KaiFa/ai_summary_app/src/app.py)**：主应用视图与调度入口。负责 Streamlit UI 视图层渲染、交互控制、定时分析调度（Cron），以及「星球内容抓取（zsxq-cli）→ AI 摘要生成 → 双引擎配图（Dreamina / Gemini Imagen）→ md2wechat 微信排版 → 公众号发布」生产管道生命周期管理。
* **[src/wechat_publisher.py](file:///f:/Jack/KaiFa/ai_summary_app/src/wechat_publisher.py)**：微信发布独立核心业务模块。实现凭证缓存与自动刷新、正文及封面图上传微信 CDN、草稿创建、群发预览及一键发布。
* **[scripts/pre_commit_guard.py](file:///f:/Jack/KaiFa/ai_summary_app/scripts/pre_commit_guard.py)**：启动前规范性自检防护脚本。基于 AST 扫描全项目（含 `src/`，项目根由其上级目录定位），拦截 `subprocess`/`os.system`/`os.popen` 动态调用 `pip`/`npm` 违规修改环境，不通过则拒绝启动。

### 配置文件与资产（config/ + src/）
* **[config/config.json](file:///f:/Jack/KaiFa/ai_summary_app/config/config.json)**：全局持久化配置（微信多账号凭证、模型/API 渠道参数、定时调度参数、图像生成引擎、网络代理等）。`app.py`/`wechat_publisher.py` 以 cwd 相对路径（`os.path.join("config", "config.json")`）读写，cwd 由 start 脚本保证=根目录。
* **[config/indicators.json](file:///f:/Jack/KaiFa/ai_summary_app/config/indicators.json)**：技术分析指标配置参数与逻辑代码存储（`INDICATORS_FILE` 同样按 `config/` 相对定位）。
* **[src/logo.png](file:///f:/Jack/KaiFa/ai_summary_app/src/logo.png)**：UI 展示 Logo 资产（`app.py` 基于 `__file__` 定位，随代码入 `src/`）。

### 启动脚本与运行环境依赖
* **[scripts/start.sh](file:///f:/Jack/KaiFa/ai_summary_app/scripts/start.sh)**：Linux (Debian) 沙箱部署脚本。cd 回项目根、`uv`/`venv` 构建、守卫校验、Dreamina CLI 下载、Playwright 安装、拉起 Streamlit。
* **[scripts/start.bat](file:///f:/Jack/KaiFa/ai_summary_app/scripts/start.bat)**：Windows 对应批处理（cd 回根自适应、守卫校验、Dreamina/Node 依赖拉取、拉起 Streamlit）。
* **[scripts/requirements.txt](file:///f:/Jack/KaiFa/ai_summary_app/scripts/requirements.txt)**：Python 第三方包核心依赖清单。
* **[package.json](file:///f:/Jack/KaiFa/ai_summary_app/package.json)**：Node 生态依赖（`zsxq-cli`、`@geekjourneyx/md2wechat`），与 `node_modules/` 同置根目录保证 npx 解析。
* **[package-lock.json](file:///f:/Jack/KaiFa/ai_summary_app/package-lock.json)**：Node 依赖锁定文件，双端版本可复现。
* **dreamina**：即梦图像生成 CLI 二进制（Linux 版由 `start.sh` 按需下载至根目录；Windows 版残留已清理，`start.bat` 保留 Windows 下载逻辑以备双端），已被 `.gitignore` 排除，属运行时资产。

### 版本管理
* **[.gitignore](file:///f:/Jack/KaiFa/ai_summary_app/.gitignore)**：Git 忽略规则（`.venv/`、`node_modules/`、`outputs/`、`tests/`、`config/`、Dreamina 二进制等）。
* **[.gitattributes](file:///f:/Jack/KaiFa/ai_summary_app/.gitattributes)**：强制 `*.sh` 使用 LF 换行符，杜绝 CRLF 导致服务器端脚本崩溃。
* **[AGENTS.md](file:///f:/Jack/KaiFa/ai_summary_app/AGENTS.md)**：项目唯一 AI 开发规则手册（详见第 11 章）。
* **Git 远程仓库**：`git@github.com:Wangbaofushuai/ai_summary_app.git`（Deploy Key 专用密钥 `/root/.ssh/ai_summary_app_ed25519`，认证配置存仓库级 `core.sshCommand`，不污染全局）。服务器项目目录为唯一真理源，推送即部署基线。

### 隔离存储目录
* **outputs/**：运行期输出。`outputs/wechat/`（推文 `*.md`/`*.html`/`.draft.json`）、`outputs/wechat/images/`（推文配图 `gemini_*.jpg`/`jimeng_*.jpg` + 长图）、`outputs/images/`（摘要长图 `summary_*.png`）、`outputs/scripts/`（短视脚本 `script_*.md`）、`outputs/indicator_docs/`（指标合规/社群手册 `*.md`/`*.docx`）、`outputs/cron_execution.log`/`manual_execution.log`/`manual_task_state.json`（Cron 与手动任务日志/状态）。
* **tests/**：完全隔离的调试测试目录，仅本地开发使用，列入同步黑名单。
* **.learnings/**：记忆协议沉淀目录（`LEARNINGS.md`、`ERRORS.md`），详见第 10 章。

## 13. 微信排版与发布常见踩坑实录

* **Go 版 md2wechat 标题字节超限**：Go 的 `len(string)` 统计字节数，UTF-8 下每个汉字 3 字节；`--title` 超过 10 个汉字即触发 `len(title) > 32` 校验崩溃。**修复原则**：调用 CLI 渲染时标题截断至 10 字内，不影响发往微信 API 的真实标题。
* **临时草稿状态丢失与污染**：刷新页面/切换文章导致草稿 ID 丢失，需重复生成。**对策**：推文同目录 `.draft.json` 绑定微信 MediaID 与 URL；公众号弹窗打开时主动加载，切换文章时清空历史缓存，杜绝状态互相污染。
