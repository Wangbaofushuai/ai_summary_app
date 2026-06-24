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
