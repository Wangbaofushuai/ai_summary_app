# 🎓 AI 架构师经验教训 (LEARNINGS.md)

本文件记录了在此次开发任务中沉淀的经验与教训，以供长期复用和参考。

## 1. Streamlit 组件状态冲突与重置问题
- **现象**：在 Streamlit 中，切换主题/模式等下拉选择框（Selectbox）需要点击两次才生效。
- **原因**：Selectbox 设置了 `key` 参数，且其默认值 `index` 绑定了一个未在组件定义前写入 session state 的动态变量。用户第一次点击引发 rerun 时，Streamlit 监测到 widget 的状态与显式传入的 `index` 参数冲突，会强制将 widget 重置为默认值。
- **解决**：在定义组件前，先初始化 session state，并将 `index` 参数绑定为该 session state 最新值，实现“一次点击即生效”。

## 2. DeepSeek 思考模式与推理强度配置
- **现象**：DeepSeek 提供带有深度思考能力的模型，其配置方法与标准 OpenAI 接口不同。
- **配置**：开启思考模式时，必须注入参数 `extra_body={"thinking": {"type": "enabled"}}` 以及指定 `reasoning_effort` 为 `"high"` 或 `"max"`。
- **重构**：应在应用中封装统一的 completions 调用器（如 `call_chat_completion`），而非在多处直接调用 `client.chat.completions.create`。并在 `generate_summary` 调用链路中透传 `chan_config` 参数。

## 3. 配置迁移逻辑与独立配置污染防范
- **现象**：历史配置数据向多渠道独立配置迁移时，如果没有限制迁移的目标渠道（如魔塔或自定义渠道），并且在迁移后没有删除原有的全局根键，那么每次切换渠道都会重新运行旧的迁移逻辑，导致各个独立渠道的配置均被复制为污染数据。
- **解决**：迁移时根据 `base_url` 关键字精准识别归属，且迁移完成后必须立即从 `config` 中 `pop` 删除历史全局字段。同时在启动时识别并重置已被污染的非归属平台配置。

## 4. 侧边栏过长与 UI 交互折叠
- **现象**：左侧栏过长导致用户需要长距离滚动，影响体验。
- **解决**：使用 `st.expander` 对不同配置分类（授权、绘图、AI、Cron）进行折叠收纳。Streamlit 不支持嵌套 expander，故原有内嵌的星球管理应改用分割线直线平铺排布。

## 5. 微信公众号爆款双线运作与金融合规体系
- **现象**：用户既需要严禁未来具体数字预测的合规宏观观察，又需要能拆解官方真实财务数据的上市公司财报深度解读。
- **解决**：重构 `get_wechat_system_prompt(orientation)`，将公共爆款文风（去 AI 味、主题色加粗、智能配图、悬浮结尾卡片）作为基底，分别针对「产业宏观」制定禁止具体数字预测与个股抽象化规则，针对「财报解读」制定三张表拆解与商业模式剖析维度，并在 UI 和 Cron 调度中实现无缝切换。

## 6. 规则主源同步滞后教训
- **现象**：接手项目审查时发现 `GEMINI.md` 主源缺失第 14 章（微信踩坑实录），而其余 6 个副本文件内容一致且已领先主源，说明此前有会话直接改了副本却漏掉主源。
- **解决**：严格遵守第 12 章纪律——任何规则修改必须先在 `GEMINI.md` 完成并全量覆盖同步所有副本；本次接手时同步更新了第 13 章目录结构（dreamina CLI、`.learnings/`、`.gitignore`/`.gitattributes`、`package-lock.json`、`outputs/` 各子目录职责等）。

## 7. 环境事实基线：AI 与项目同机运行于 Linux 服务器
- **事实**：AI 部署于 Linux (Debian) 服务器，用户通过公网 IP Web 界面交互；项目用途为学习测试，无需金融合规级安全加固，但“宿主机零污染”是不可放弃的底线。
- **行动**：手册第 2 章已由“Windows 本地为主 + WinSCP 单向同步”改为“服务器为唯一工作环境、直接落盘”的现行事实；新增强调“任务启动前盘点 Skills/MCP/CLI 资源并适时调用”“宿主机越界操作先申请用户决定”“任务前后双清根目录”等纪律。

## 8. 规则文件精简为 AGENTS.md 单文件
- **事实**：纯 Linux 开发环境，用户认为多平台规则副本无用；历史遗留 6 个副本（GEMINI.md / AI_DEVELOPMENT_RULES.md / CLAUDE.md / .clauderules / .cursorrules / .agents/rules/AI_DEVELOPMENT_RULES.md）已全部删除。
- **行动**：第 12 章重写为“规则手册唯一文件机制”，`AGENTS.md` 成为唯一规则文件（直接修改、无副本同步）；第 6/13 章白名单同步收编；`pre_commit_guard.py` 违规提示文案改为引用 `AGENTS.md`。

## 9. 技能体系与 Windows 残留一并移除
- **事实**：技能（agent-memory/skill-creator/self-improving 等）经核实仅服务 AI 辅助开发、Web 程序零引用，用户要求一并删除：`.agents/skills/`、`skills/`、旧会话残渣（BRIEFING/handoff/teamwork_preview_*）、Windows 残留（`dreamina.exe`、`.dreamina_cli/`）均已清理。
- **行动**：第 11 章改为“技能库已移除，如需经 `.skillhub/skills_store_cli.py --dir skills` 重建 + 手动建立 `.agents/skills` 链接”，记忆协议保留纯文件读写方式（直接读写 `.learnings/`）；start.sh/start.bat 移除 skills 链接逻辑；.gitignore 移除 `.agents/skills/`；第 13 章目录结构同步。注意：Linux 版 `./dreamina` 现缺失，首个 `./start.sh` 运行时会自动下载。

## 10. 核心保留 / 杂项清除收尾
- **用户决策**：`.learnings/` 保留（AI 经验记忆收益大于成本）；`.skillhub/`、`tests/` 与 `outputs/` 历史文件删除（保留目录骨架，程序日志/状态文件均有自动重建 fallback，已确认 `get_manual_task_state` 有默认值、`write_cron_log` 有 makedirs）；`start.bat` 与第 8 章双端规则保留（用户选择继续维持双平台兼容）。
- **行动**：删除 `.skillhub/`，清空 `tests/` 与 `outputs/`（重建 `images`/`scripts`/`indicator_docs`/`wechat/images` 空骨架），AGENTS.md 第 6/7/11/13 章同步移除 SkillHub 痕迹；守卫与 app.py 语法验证通过。

## 11. 目录结构整合为 src/ 模块化 + 规则贴合现状
- **事实**：AGENTS.md 残留引用未挂载的 `/sequential-thinking` MCP 与 SkillHub 规则；`app.py`/`wechat_publisher.py`/`logo.png` 散在根目录。
- **行动**：核心代码迁入 `src/`（`src/app.py`、`src/wechat_publisher.py`、`src/logo.png`）；`logo.png` 因 `app.py` 以 `__file__` 定位而零改动迁移；`config.json`/`indicators.json`/`outputs/` 均以进程 cwd（start 脚本工作目录=根目录）相对定位，保持根目录零迁移；`start.sh`/`start.bat` 启动行改为 `src/app.py`；守卫 `pre_commit_guard.py` 留根目录（rglob 自动覆盖 `src/`）。
- **规则**：第 7 章改为"当前未挂载 MCP，独立深度思考"；第 6/11/13 章全部贴合现状；smoke test（streamlit run src/app.py --port 3999 headless）启动成功，临时进程已清理无残留。

## 12. 目录终局格局：config/ + scripts/ + src/ 三目录化
- **事实**：用户要求根目录零 py/js 散落——根目录只剩规则/依赖清单/隔离目录。
- **行动**：`config.json`+`indicators.json` → `config/`（`app.py` 的 `CONFIG_FILE`/`INDICATORS_FILE`、`wechat_publisher.py` 的 `load_accounts`/`save_accounts` 默认参数统一改为 `os.path.join("config", ...)`）；`start.sh`/`start.bat`/`pre_commit_guard.py` → `scripts/`（start 脚本顶部加 `cd "$(dirname "$0")/.."` / `cd /d "%~dp0.."` 自适应回根目录保证 cwd=根目录；守卫 `project_root = Path(__file__).parent.parent`）；`.gitignore` 改为 `config/` 整目录忽略。package.json/package-lock/node_modules 三者必须同居根目录以保 npx 解析，不可迁移。
- **经验**：smoke test 唤醒 `streamlit` 需用 `timeout` 短跑 + `pgrep -f` 清理派生进程，防幽灵进程残留；守卫扫描范围依赖 `project_root` 定位，脚本迁移时必须同步修正。

## 13. requirements.txt 收编 + Node 三件套保持根目录（用户决策）
- **事实**：根目录当时仅剩 `package.json`/`package-lock.json`/`requirements.txt` 三个清单；用户问"为什么不整合"。
- **决策**：`requirements.txt` 零约束 → 移入 `scripts/requirements.txt`（start.sh/start.bat 引用路径同步）；`package.json`/`package-lock.json` 与 `node_modules/` 三体绑定（npx 从 cwd 向上解析、app.py 共 10 处 `npx zsxq-cli/md2wechat` 调用），用户确认**保持现状**——整合须改 10 处调用为显式 `.bin/` 路径并双端兼顾，且无法离线验证授权链路，不建议零散插队执行。
- **教训**：Node 生态下"依赖清单/锁定文件/安装产物"必须同目录，这是 npx 解析的硬约束，在目录整洁与运行稳定冲突时优先保持稳定。
