# ❌ 错误细节与排查日志 (ERRORS.md)

本文件记录了在开发中遇到的错误及解决方案，防范未来重蹈覆辙。

## 1. Streamlit Widget Reversion Error
- **错误**：Widget state resets to original value on first change.
- **分类**：前端状态机同步问题
- **修复**：在组件调用之前，在 `st.session_state` 中同步最新的数据；确保 widget 的 `index` 参数引用的始终是已更新的 `st.session_state` 键值。

## 2. DeepSeek Chat API Invalid Parameters
- **错误**：当思考模式启用时，若传入不支持的 temperature / top_p 导致 API 报错。
- **分类**：第三方 API 限制
- **修复**：在 completions 封装中过滤掉不支持的参数，仅使用 `extra_body` 参数控制思考。

## 3. Configuration Overwrite on Startup
- **错误**：切换 AI 渠道后，发现密匙和 Base URL 仍是其他渠道的值。
- **原因**：历史迁移逻辑每次运行都将全局旧配置（ModelScope）强行覆盖至当前选定的 platform。
- **修复**：限定迁移范围，并及时 `pop` 删除 `config.json` 的历史根配置字段。

## 4. Test Run Bypassed by Auto-Run Switch
- **错误**：手动点击“测试运行任务”时，任务没有启动且无日志输出。
- **原因**：底层调度入口函数硬编码了 `if not auto_run: return`，导致定时开关关闭时手动测试运行直接被静默丢弃。
- **修复**：为调度函数添加 `ignore_auto_run: bool = False` 参数，并在手动测试运行时透传 `ignore_auto_run=True`。

## 5. ZSXQ-CLI TLS Handshake Timeout on Server
- **错误**：Debian 服务器调用 `zsxq-cli` 时报错 `net/http: TLS handshake timeout`。
- **原因**：某些云服务器/海外 VPS 节点的 IP 访问 `mcp.zsxq.com:443` 时被安全网关 (WAF) 丢包阻断，且 `subprocess.run` 未注入代理环境变量。
- **修复**：实现 `get_exec_env()` 辅助函数提取 `network_proxy` 配置注入 `HTTP_PROXY` / `HTTPS_PROXY`，并在侧边栏提供代理设置项与故障诊断工具引导。

## 6. Overly Broad Keyword Filter & Missing Image Injection
- **错误**：推文生成频繁误报 `包含 '我无法'` 并放弃推送，且有时未调用生图。
- **原因**：① 校验词库中的 `"我无法"` 过于短泛，误判了正文中中立合规免责声明；② 大模型有时写推文遗漏 `[IMAGE_GENERATE:]` 标记导致无法触发生图；③ 生成被拦后缺少重试机制。
- **修复**：① 精细化拒答词库为完整拒答句式；② 增加 `ensure_image_prompts_exist` 配图保底补全机制；③ 增加 `max_retries = 2` 重新生成重试循环。
