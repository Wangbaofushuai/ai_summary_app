# 🤖 AI 架构师开发手册 (AI_DEVELOPMENT_RULES)

> **最高指导原则**：在任何版本迭代、Bug 修复和新功能开发中，所有参与该项目维护的 AI 架构师必须绝对遵守本手册列出的所有纪律，防止代码冲突与环境污染。

## 1. 项目身份设定
* **核心架构**：基于 Python 编写的核心逻辑，搭配 Streamlit 驱动的 Web 交互界面。
* **依赖生态**：融合了 Python 标准数据流、Playwright（自动化渲染）、以及 Node.js 生态的第三方 CLI 工具（如 `zsxq-cli`）。
* **双端要求**：需要提供极致的代码便携性与兼容性，确保同一套源码可同时在 Windows 和 Debian 环境下稳定运行。

## 2. DevOps 同步架构 (核心生命线)
* **本地为主**：所有的代码变更、调试与功能重构，**必须且只能在本地 Windows 环境上完成**。
* **单向覆盖同步**：底层挂载了 WinSCP 自动化工具，将本地变动实时单向覆盖到 Debian 服务器。
* **防逆向污染**：由于双端环境相互独立，**绝对禁止**服务器端代码反向同步。本地环境是唯一真理，所有逻辑必须基于本地测试。

## 3. 绿色的“沙箱隔离”原则
坚守“随走随删，不留痕迹”的环境纯净度：
* **彻底的局部环境**：本地开发与调试时，必须绝对锁定根目录下的 `.venv`。严禁修改宿主机的系统全局环境变量，严禁使用全局命令如 `npm install -g`。
* **依赖管理升级**：本项目全面推荐使用 `uv` 进行依赖管理（使用 `uv venv` 和 `uv pip install` 代替传统的 `python -m venv` 和 `pip install`，以追求极致的部署速度）。
* **同步黑名单**：考虑到跨平台的二进制差异，`node_modules/`、`.venv/`、`__pycache__/` 等本地运行库和缓存文件夹已被加入了 WinSCP 传输黑名单，它们仅供本地使用。服务端将在 `start.sh` 内独立拉起自己的隔离依赖。

## 4. 跨平台防爆纪律
* **绝对安全的路径操作**：跨平台项目严禁硬编码包含 `\` 或 `/` 的静态路径分隔符。所有的路径拼接和处理，**必须无条件使用 `pathlib.Path` 或 `os.path.join()`**。
* **Linux 格式的 Shell 脚本**：创建或修改任何用于服务器执行的 Shell 脚本（如 `start.sh`）时，**换行符必须被强制保存为 `LF`（Linux 格式）**。如果在 Windows 平台下编辑，切忌引入 `CRLF`。

## 5. 启动与测试规范
严禁使用 `python app.py` 作为启动命令。为保障隔离沙箱的完整激活：
* **本地测试 (Windows)**：执行 `.\start.bat`。该批处理会挂载虚拟环境、装载局部 Node CLI，并调用 `streamlit run app.py`。
* **远程部署 (Debian)**：执行 `./start.sh`。该脚本负责在服务器上独立构建专属沙箱并拉起进程。

## 6. 项目文件结构纪律与目录整洁规范
* **目录整洁与归整红线**：项目根目录必须保持极度整洁。
  1. 根目录仅允许保留核心代码文件（如 `app.py`）、系统启动脚本（如 `start.bat`/`start.sh`）、必要的环境/依赖/配置描述文件（如 `requirements.txt`/`package.json`/`indicators.json`/`config.json`）、AI 规则手册文件（`GEMINI.md`/`AGENTS.md`/`AI_DEVELOPMENT_RULES.md`/`CLAUDE.md`）、项目资产（如 `logo.png`）以及 `.agents/` / `.skillhub/` / `.venv/` / `skills/` 等系统隔离文件夹。
  2. 严禁在项目根目录下生成或散落任何非必要的临时文件、运行缓存、调试图片（如 `cat.jpg`、`test_cat.jpg`）或测试脚本。所有的测试素材和临时调试脚本必须全部移动到 `tests/` 目录。
  3. 所有应用运行生成的临时文件、长图和文档输出必须隔离在 `outputs/` 目录中。
* **测试与临时文件隔离**：所有测试脚本、调试输出文件、临时生成的文档，**必须**放置在项目根目录下的 `tests/` 文件夹内。严禁在项目根目录散落测试文件（如 `test.py`、`test.docx`、`stderr.txt` 等）。
* **模块化结构化开发原则**：在开发新功能时，绝对禁止将所有逻辑全都堆砌在 `app.py` 中。必须按照功能模块进行标准结构化设计（例如将微信发布、多账号管理等独立业务封装在独立的 Python 模块中，如 `wechat_publisher.py`），以保持 `app.py`（Streamlit 视图层）的清爽和可维护性。
* **同步黑名单补充**：`tests/` 文件夹应加入 WinSCP 传输黑名单，仅供本地开发调试使用，不参与服务器同步。
* **项目目录结构同步纪律**：每次在项目中增添或重构新的模块内容与文件时，**必须且只能**先将最新项目目录结构和各文件职责说明同步更新到本手册的「13. 项目目录结构与职责说明」章节中，随后将其完整覆盖同步到所有副本规则文件，以确保 AI 架构师时刻掌握最新的项目布局与修改入口，杜绝盲目改动。


## 7. AI 架构师强制思维纪律
* **回答前强制调用思考模型**：在回答用户的任何问题、进行代码编写或方案设计之前，AI 必须**强制且优先调用 `/sequential-thinking` MCP 工具**。
* **拒绝鲁莽回复**：通过该工具进行深度拆解、逻辑推演和可行性分析后，方可向用户输出正式回复或采取动作。此举旨在绝对避免仓促的代码修改引发金融合规风险或底层架构冲突。

## 8. 跨平台兼容级红线（Linux & Windows 双端强制）
> **核心原则**：本项目的任何一行代码、任何一个新增功能、任何一次依赖引入，都必须同时在 **Windows** 和 **Linux (Debian)** 双平台上可用。这是不可逾越的红线。
* **新增功能双端验证**：每次添加新功能或引入新的外部工具/CLI 时，**必须同时考虑并实现 Windows 与 Linux 两套路径**。例如，Windows 使用 `.exe` 后缀的可执行文件，Linux 使用无后缀二进制，需通过 `sys.platform` 判断并分别处理。
* **启动脚本双端同步**：涉及环境初始化、依赖下载、CLI 工具拉取等操作时，**必须同时更新 `start.bat`（Windows）和 `start.sh`（Linux）**，禁止只改一端而遗漏另一端。
* **不可兼容时的强制告知义务**：如果某个操作或依赖确实无法兼容双平台（如仅 Windows 可用的 COM 组件、仅 Linux 可用的 systemd 服务等），AI **必须在执行前主动告知用户**，明确说明：① 将要执行的操作；② 不兼容的具体原因；③ 对另一端的影响；④ 是否有替代方案。**严禁静默执行单平台操作。**
* **路径分隔符零容忍**：重申规则 #4，所有路径操作必须使用 `os.path.join()` 或 `pathlib.Path`，绝对禁止硬编码 `\` 或 `/`。

## 9. 强制计划书制度（流程树 + 打勾确认）
> **核心原则**：任何非 trivial 的功能新增、架构变更或 Bug 修复，AI 都必须先产出一份**计划书（Implementation Plan）**，经用户审批后才可动手执行。严禁未经批准就直接修改代码。
* **计划书内容要求**：
  1. **目标描述**：用通俗语言说明本次变更要解决什么问题、达成什么效果。
  2. **整体业务/技术逻辑构思**：以流程树或分层列表的形式，梳理出所有需要变动的模块、文件及其依赖关系。
  3. **任务清单（Checklist）**：将所有步骤拆分为可勾选的 `[ ]` 任务项，执行过程中逐一打 `[x]` 确认完成。
  4. **跨平台影响评估**：明确标注哪些改动涉及双平台、是否需要同步更新 `start.bat` / `start.sh`。
  5. **验证方案**：说明如何测试和验证变更效果。
* **执行纪律**：
  - **中文化书写纪律**：所有的计划书（Implementation Plan）、任务树/任务清单（Checklist）必须无条件以**中文（简体中文）**形式展示与编写。
  - 计划书必须以 Artifact 形式呈现，设置 `RequestFeedback = true` 等待用户批准。
  - 用户批准后，AI 创建 `task.md` 跟踪执行进度，每完成一步即时打勾。
  - 执行完毕后，输出 `walkthrough.md` 总结变更内容与验证结果。


## 10. 防退化与主动沟通规范（Anti-Regression & Proactive Communication）
> **核心原则**：修改一个 BUG 时，绝对不能引发新的 BUG。当面临需求模糊、发现潜藏风险或不知如何处理时，不要擅自做主，必须主动向用户发起提问。
* **修改前的副作用评估**：在修改任何代码之前，必须思考“这段逻辑是否被其他模块复用？”“这里的改动是否会导致原本正常工作的 UI 崩溃、阻塞或报错？”。例如在 Streamlit 的循环或渲染主流程中加入阻塞型调用（subprocess），极大概率会导致全局点击卡顿。
* **主动提问机制**：如果用户的指令不明确，或者你在代码中发现更好的重构方向、潜在的隐患，**必须**在执行或返回前告诉用户：“我认为这里可以怎么做...”或“这么做会有...的风险，请问你希望我怎么处理？”。
* **失败兜底（Fallback）**：在调用外部 API、第三方 CLI 时，必须假定其有极高概率失败。所有容易失败的环节必须添加 try-catch 和 Fallback 机制（如图片生成失败则渲染本地占位图并给予文字提示，绝不能让整个渲染管道崩溃或呈现空白）。
* **越界操作的告知红线**：如果因用户明确指定、系统配置或依赖需要，而不得不做出违反“沙箱隔离”原则（如在项目根目录外进行全局安装、修改全局系统环境配置、或读写系统关键目录等）的越界操作，AI **必须在执行前主动告知用户**，详尽披露：① 计划执行的具体命令；② 该操作涉及的外部全局路径或修改；③ 对宿主机系统或全局环境造成的持久化影响。严禁静默执行此类越界操作。

## 11. SkillHub 与技能商店协同增智机制
* **能力与智力扩展**：AI 必须积极、充分地运用已部署的 SkillHub 命令行工具与安装的 `skill-creator` 技能来持续提升和扩充自身的逻辑架构能力。
* **沙箱局部隔离要求**：SkillHub CLI (`skills_store_cli.py`) 和安装的所有技能（如 `skill-creator`）必须全部存放在项目局部的 `.skillhub/` 和 `skills/` 目录下。任何时候使用 SkillHub 进行安装或升级，必须显式指定 `--dir skills` 参数，绝对禁止写入宿主机的全局 `~/.openclaw` 或其他外部环境变量目录。
* **技能生效与自动加载机制**：由于 AI 运行环境（如 Google Antigravity / Gemini CLI）只从 `.agents/skills/`（或 `.gemini/skills/`）读取并激活技能，因此必须在启动脚本中配置目录连结（Windows 用 Junction，Linux 用 Symlink），把项目级加载路径 `.agents/skills` 映射到本地存放目录 `skills`，实现安装即自动生效。
* **技能开发规范与主动加载**：当 AI 需要定义新技能、创建新的工具集成或优化工作流时，应当主动并优先通过读取 `skills/skill-creator` 技能（或直接查看 `.agents/skills/skill-creator/SKILL.md`）或调用局部 SkillHub 命令获取最佳实践，并严格遵循其编写 `SKILL.md`。在匹配到用户相关任务时，必须优先载入对应 Skill 的规则并加以严格执行，拒绝装完后搁置。
* **智能体记忆协议 (Memory Protocol) 规约**：在每个会话/任务的生命周期中，AI 必须严格遵循 `agent-memory` 技能的记忆协议以沉淀项目经验：
  - **会话/任务启动时**：① 从记忆中加载最近 5 条教训（如调用 `mem.get_lessons(limit=5)` 或查阅本地已生成的 `.learnings/LEARNINGS.md` / `~/self-improving/`）；② 核对当前任务涉及的实体（Entity）上下文；③ 回忆并载入相关的历史事实。
  - **会话/任务结束时**：① 从本次会话中提取出具备长期复用价值的持久事实；② 记录本次任务学到的所有经验教训与错误细节（如写入 `.learnings/ERRORS.md`）；③ 更新涉及的实体状态与偏好信息。




## 12. 规则手册同步机制（多平台 AI 上下文统一）
> **核心原则**：`GEMINI.md` 是本项目 AI 开发手册的**唯一主源文件（Single Source of Truth）**。所有其他平台的规则副本文件均从该文件派生，任何规则修改**必须先在 `GEMINI.md` 上进行**，完成后**立即同步覆盖**到所有副本文件。
* **主文件**：`GEMINI.md`（项目根目录）—— Google Antigravity (Gemini) 的工作区上下文规则文件，同时也是本手册的权威版本。
* **从文件（必须与主文件保持内容完全一致）**：
  1. `AGENTS.md`（项目根目录）—— 通用 Agent 工作区上下文规则文件。
  2. `AI_DEVELOPMENT_RULES.md`（项目根目录）—— 人类可读的手册归档副本。
  3. `CLAUDE.md`（项目根目录）—— Claude 系列 AI 的工作区上下文规则文件。
  4. `.clauderules`（项目根目录）—— Claude Code 的旧版规则文件。
  5. `.cursorrules`（项目根目录）—— Cursor IDE 的规则文件。
  6. `.agents/rules/AI_DEVELOPMENT_RULES.md` —— IDE Agent 规则目录副本。
* **同步纪律**：
  - 每次修改手册内容后，AI **必须立即将 `GEMINI.md` 的完整内容逐字覆盖写入上述所有从文件**，确保全平台规则零差异。
  - 严禁仅修改某一个副本而遗漏其他文件。
  - 此规则本身也受版本管理保护，禁止被静默删除或弱化。

## 13. 项目目录结构与职责说明

本项目采用结构化与模块化的设计，各核心文件及目录职责划分如下，以便 AI 架构师快速定位并进行修改：

### 核心代码与业务逻辑
* **[app.py](file:///f:/Jack/KaiFa/ai_summary_app/app.py)**：主应用视图与调度入口。负责 Streamlit UI 视图层渲染、交互控制逻辑、定时分析调度逻辑（Cron）、以及整体分析发布管道的生命周期管理。
* **[wechat_publisher.py](file:///f:/Jack/KaiFa/ai_summary_app/wechat_publisher.py)**：微信发布独立核心业务模块。实现微信接口凭证缓存与自动刷新、正文及封面图片上传微信 CDN、草稿箱草稿创建、群发预览发送及一键正式发布的核心逻辑。
* **[pre_commit_guard.py](file:///f:/Jack/KaiFa/ai_summary_app/pre_commit_guard.py)**：项目启动前的环境依赖与规范性自检防护脚本。

### 配置文件与资产
* **[config.json](file:///f:/Jack/KaiFa/ai_summary_app/config.json)**：应用全局持久化配置文件（管理微信多账号凭证、各模型/API 渠道参数、定时调度参数等）。
* **[indicators.json](file:///f:/Jack/KaiFa/ai_summary_app/indicators.json)**：持久化存储技术分析指标的配置参数与逻辑代码文件。
* **[logo.png](file:///f:/Jack/KaiFa/ai_summary_app/logo.png)**：系统 UI 界面使用的展示 Logo 资产。

### 启动脚本与环境依赖
* **[start.bat](file:///f:/Jack/KaiFa/ai_summary_app/start.bat)**：Windows 环境下激活虚拟环境、链接技能、校验启动守卫并拉起 Streamlit 服务的批处理脚本。
* **[start.sh](file:///f:/Jack/KaiFa/ai_summary_app/start.sh)**：Linux (Debian) 环境下沙箱隔离部署与后台运行进程的服务端启动脚本。
* **[requirements.txt](file:///f:/Jack/KaiFa/ai_summary_app/requirements.txt)**：Python 环境第三方包的核心依赖清单。
* **[package.json](file:///f:/Jack/KaiFa/ai_summary_app/package.json)**：Node.js 生态依赖配置文件（主要用于引入 `zsxq-cli` 及 `@geekjourneyx/md2wechat` 依赖）。

### 隔离存储目录
* **outputs/**：运行期输出文件夹。
  * `outputs/wechat/`：存放分析生成的历史推文 Markdown 原始文件 (`*.md`) 及 md2wechat 渲染的美化版 HTML 文件 (`*.html`)。
  * `outputs/wechat/images/`：存放生成的所有推文本地配图（文件名格式如 `gemini_xxxx.jpg`，`jimeng_xxxx.jpg`）以及高保真长图 (`*.png`)。
* **tests/**：完全隔离的调试测试目录，用于存放所有临时测试脚本及本地开发调试日志，已被移入同步黑名单。
* **.agents/** / **skills/** / **.skillhub/**：定制 AI 智能体开发规范、技能逻辑和局部技能商店存储目录。


