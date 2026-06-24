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
