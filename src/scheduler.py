import os
import re
import json
import subprocess
import time
import traceback
import glob
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import image_engine
import llm
import prompts
import wechat_render
import wechat_publisher
import zsxq_client
from config_store import load_config as _load_config, load_indicators as _load_indicators, get_exec_env as _get_exec_env

NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"
WECHAT_OUTPUT_DIR = os.path.join("outputs", "wechat")
SCRIPT_OUTPUT_DIR = os.path.join("outputs", "scripts")
INDICATOR_DOCS_DIR = os.path.join("outputs", "indicator_docs")
MANUAL_TASK_STATE_FILE = os.path.join("outputs", "manual_task_state.json")
MANUAL_LOG_FILE = os.path.join("outputs", "manual_execution.log")

_scheduler = None

def get_scheduler():
    """模块级单例 APScheduler（原 @st.cache_resource 去装饰化为懒加载单例）"""
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler

def _get_exec_env():
    env = os.environ.copy()
    try:
        with open(os.path.join("config", "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        proxy = cfg.get("network_proxy", "")
        if proxy:
            env["HTTP_PROXY"] = proxy
            env["HTTPS_PROXY"] = proxy
            env["http_proxy"] = proxy
            env["https_proxy"] = proxy
    except Exception:
        pass
    return env

def write_cron_log(msg):
    log_path = os.path.join("outputs", "cron_execution.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

def get_manual_task_state():
    """读取当前手动分析任务状态"""
    if os.path.exists(MANUAL_TASK_STATE_FILE):
        try:
            with open(MANUAL_TASK_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "idle", "stop_requested": False, "msg": ""}

def save_manual_task_state(status="idle", stop_requested=False, msg="", error="", started_at=None, **kwargs):
    """保存手动分析任务状态"""
    os.makedirs("outputs", exist_ok=True)
    state = {
        "status": status,  # "running", "success", "error", "stopped", "idle"
        "stop_requested": stop_requested,
        "msg": msg,
        "error": error,
        "started_at": started_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(MANUAL_TASK_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state

def request_stop_manual_task():
    """请求终止当前手动任务"""
    state = get_manual_task_state()
    state["stop_requested"] = True
    state["msg"] = "用户已在界面触发停止任务请求"
    save_manual_task_state(**state)

def write_manual_log(msg: str):
    """写入手动任务持久化日志"""
    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}\n"
    with open(MANUAL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted)

def clear_manual_log():
    """清空手动任务日志"""
    os.makedirs("outputs", exist_ok=True)
    with open(MANUAL_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

def run_manual_deep_analysis_worker(curr_group_id, l_limit, s_key, current_chan_config, a_mode, use_p_ui, cp_text, use_wechat, also_generate_report, wechat_prompt, config):
    """手动深度分析后台解耦 worker 进程/线程，独立运行不受 Streamlit F5 刷新影响"""
    import os
    import json
    import re
    import time
    from datetime import datetime
    
    save_manual_task_state(status="running", msg="任务拉起中...")
    clear_manual_log()
    write_manual_log("==================================================")
    write_manual_log("[手动深度分析] 后台进程工作线程拉起成功 (解耦模式，F5 刷新防中断)")
    
    def check_stop():
        st = get_manual_task_state()
        return st.get("stop_requested", False)

    try:
        if check_stop():
            write_manual_log("🛑 收到终止信号，任务已在初始化阶段中断。")
            save_manual_task_state(status="stopped", msg="任务被终止")
            return

        def update_progress(event):
            if check_stop(): return
            if event['type'] == 'info':
                write_manual_log(f"ℹ️ {event['msg']}")
            elif event['type'] == 'topic_start':
                preview_text = re.sub(r'<[^>]+>|<[^>]*$', '', event['preview'])
                write_manual_log(f"⏳ 处理话题: `{preview_text}`")
            elif event['type'] == 'topic_log':
                write_manual_log(f"　 └─ {event['msg']}")
            elif event['type'] == 'topic_end':
                if event.get('success'):
                    write_manual_log("　 └─ ✅ 完成")
                else:
                    reason = event.get('reason', '')
                    write_manual_log(f"　 └─ ⏭️ 跳过 ({reason})")

        write_manual_log(f"正在获取知识星球动态 (范围: {s_key}, 数量: {l_limit})...")
        raw, f_list, briefs = zsxq_client.fetch_zsxq(curr_group_id, limit=l_limit, scope=s_key, progress_callback=update_progress)
        
        if check_stop():
            write_manual_log("🛑 收到终止信号，抓取阶段后中断。")
            save_manual_task_state(status="stopped", msg="任务被终止")
            return
            
        if raw.startswith("获取失败") or raw.startswith("获取异常") or raw.startswith("跳过分析") or (not briefs and not f_list):
            write_manual_log(f"❌ 数据抓取失败或无需分析: {raw}")
            save_manual_task_state(status="error", error=f"数据抓取失败: {raw}")
            return

        write_manual_log(f"🧠 正在向大模型发起深度分析 (模型: `{current_chan_config.get('selected_model')}`)...")
        res_main = llm.generate_summary(raw, current_chan_config.get("api_key"), current_chan_config.get("base_url"), current_chan_config.get("selected_model"), a_mode, chan_config=current_chan_config)
        
        if check_stop():
            write_manual_log("🛑 收到终止信号，大模型第一阶段分析后中断。")
            save_manual_task_state(status="stopped", msg="任务被终止")
            return
            
        if res_main.startswith("AI 总结失败") or res_main.startswith("未提供"):
            write_manual_log(f"❌ 深度分析失败: {res_main}")
            save_manual_task_state(status="error", error=res_main)
            return

        final_res = res_main
        if use_p_ui and cp_text:
            write_manual_log("✨ 正在执行个性化二次美化加工...")
            final_res = llm.generate_summary(res_main, current_chan_config.get("api_key"), current_chan_config.get("base_url"), current_chan_config.get("selected_model"), a_mode, custom_prompt=cp_text, chan_config=current_chan_config)
            if check_stop():
                write_manual_log("🛑 收到终止信号，二次美化阶段后中断。")
                save_manual_task_state(status="stopped", msg="任务被终止")
                return
            if final_res.startswith("AI 总结失败"):
                write_manual_log(f"❌ 二次美化加工失败: {final_res}")
                save_manual_task_state(status="error", error=final_res)
                return
                
        if use_wechat:
            write_manual_log("📱 正在创作微信公众号推文 (包含智能配图)...")
            is_src_valid, src_reason = wechat_render.validate_wechat_article_content(final_res)
            if not is_src_valid:
                write_manual_log(f"⚠️ 源文本质量校验未通过 ({src_reason})，放弃微信推文生成。")
                save_manual_task_state(status="error", error=src_reason)
                return

            wechat_orientation = config.get("wechat_article_orientation", "产业宏观与行业趋势")
            write_manual_log(f"🧭 推文内容定位：【{wechat_orientation}】")
            wechat_system_prompt = prompts.get_wechat_system_prompt(wechat_orientation)
            wechat_user_content = f"【基础分析总结】\n{final_res}\n"
            if wechat_prompt.strip():
                wechat_user_content += f"\n【用户个性化要求】\n{wechat_prompt}"
                
            from openai import OpenAI
            client = OpenAI(api_key=current_chan_config.get("api_key"), base_url=current_chan_config.get("base_url") if current_chan_config.get("base_url") else None)
            wc_response = llm.call_chat_completion(client, current_chan_config.get("selected_model"), [{"role": "system", "content": wechat_system_prompt}, {"role": "user", "content": wechat_user_content}], chan_config=current_chan_config)
            
            if check_stop():
                write_manual_log("🛑 收到终止信号，微信推文生成后中断。")
                save_manual_task_state(status="stopped", msg="任务被终止")
                return

            if wc_response.choices and wc_response.choices[0].message.content:
                raw_wechat = wc_response.choices[0].message.content
                is_wc_valid, wc_reason = wechat_render.validate_wechat_article_content(raw_wechat)
                if not is_wc_valid:
                    write_manual_log(f"⚠️ 微信推文安全审查未通过 ({wc_reason})，取消保存与发布！")
                    save_manual_task_state(status="error", error=wc_reason)
                    return

                raw_wechat = image_engine.ensure_image_prompts_exist(raw_wechat)
                raw_wechat = image_engine.adjust_markdown_images_placement(raw_wechat)
                
                def replace_img(match):
                    if check_stop(): return ""
                    kw = match.group(1)
                    img_engine_str = config.get("image_generator", "即梦 (Dreamina)")
                    if img_engine_str == "Google Gemini (Imagen 3)":
                        write_manual_log(f"🖼️ 正在调用 Gemini 生成配图: `{kw}`")
                        img_path = image_engine.generate_gemini_image(
                            kw, 
                            config.get("google_api_key", ""), 
                            model_name=config.get("gemini_image_model", "imagen-4.0-generate-001"),
                            aspect_ratio=config.get("image_aspect_ratio", "1:1")
                        )
                    else:
                        write_manual_log(f"🖼️ 正在调用即梦生成配图: `{kw}`")
                        img_path = image_engine.generate_jimeng_image(kw)
                    time.sleep(1.0) # 安全冷却间隔，防止并发冲高耗尽套接字端口
                    if img_path:
                        img_path = img_path.replace("\\", "/")
                        return f"({img_path})"
                    return "(https://dummyimage.com/800x400/ffebee/d32f2f.png&text=Image+Generate+Failed)"

                wechat_res = re.sub(r'\(\[IMAGE_GENERATE:(.*?)\]\)', replace_img, raw_wechat)
                
                if check_stop():
                    write_manual_log("🛑 收到终止信号，配图替换阶段中断。")
                    save_manual_task_state(status="stopped", msg="任务被终止")
                    return

                # 保存推文到文件
                wc_filename = f"wechat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                wc_path = os.path.join(WECHAT_OUTPUT_DIR, wc_filename)
                with open(wc_path, "w", encoding="utf-8") as f:
                    f.write(wechat_res)
                    
                write_manual_log("🎨 正在使用 md2wechat 进行样式美化排版...")
                theme = config.get("wechat_theme", "spring-fresh" if "AI" in config.get("wechat_mode", "AI 模式") else "default")
                mode_ui = config.get("wechat_mode", "AI 模式 (免费)")
                api_key = config.get("md2wechat_api_key", "")
                font_size = config.get("wechat_font_size", "medium")
                bg_type = config.get("wechat_background_type", "none")
                custom_prompt = config.get("wechat_custom_prompt", "")
                
                html_res = wechat_render.convert_to_wechat_html(
                    wechat_res, theme, mode_ui, 
                    api_key=api_key, font_size=font_size, 
                    bg_type=bg_type, chan_config=current_chan_config, 
                    custom_prompt=custom_prompt
                )
                html_filename = wc_filename.replace(".md", ".html")
                html_path = os.path.join(WECHAT_OUTPUT_DIR, html_filename)
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_res)
                write_manual_log(f"🎉 微信推文生成成功并保存到: {html_path}")

        if not use_wechat or also_generate_report:
            write_manual_log("🎨 正在渲染专业分析报表图片...")
            img_p = image_engine.render_to_image(final_res, a_mode)
            write_manual_log(f"🎉 分析报表图片生成成功并保存到: {img_p}")

        write_manual_log("==================================================")
        write_manual_log("✅ 手动深度分析任务全部顺利完成！")
        save_manual_task_state(status="success", msg="分析任务顺利完成")
    except Exception as e:
        write_manual_log(f"❌ 后台任务异常抛出: {str(e)}")
        save_manual_task_state(status="error", error=str(e))

def run_scheduled_wechat_publish(draft_file_path: str):
    """定时群发公众号推文的核心执行逻辑（被 APScheduler 异步调用）"""
    import os
    import json
    import datetime
    import traceback
    
    write_cron_log(f"==================================================")
    write_cron_log(f"[定时群发公众号] 定时群发任务启动，关联文件: {draft_file_path}")
    
    if not os.path.exists(draft_file_path):
        write_cron_log(f"[定时群发公众号] 错误：找不到草稿关联 JSON 文件 {draft_file_path}")
        return
        
    try:
        with open(draft_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        media_id = data.get("media_id")
        appid = data.get("appid")
        secret = data.get("secret")
        url = data.get("url")
        status = data.get("status")
        publish_mode = data.get("publish_mode", "publish")  # "mass_send" 或 "publish"
        
        if not media_id or not appid or not secret:
            write_cron_log(f"[定时群发公众号] 错误：JSON 数据不全 (media_id: {media_id}, appid: {appid})")
            return
            
        if status == "published":
            write_cron_log(f"[定时群发公众号] 提示：该文章此前已发布，跳过本次群发。")
            return
            
        # 1. 获取微信凭证
        write_cron_log(f"[定时群发公众号] 正在获取 Access Token (AppID: {appid[:6]}...)")
        token = wechat_publisher.get_access_token(appid, secret)
        
        # 2. 正式群发 / 发布
        if publish_mode == "mass_send":
            write_cron_log(f"[定时群发公众号] 正在正式群发 MediaID: {media_id} ...")
            try:
                pub_id = wechat_publisher.mass_send_draft(token, media_id)
                write_cron_log(f"[定时群发公众号] 成功：已正式群发！消息ID: {pub_id}")
            except Exception as e:
                write_cron_log(f"[定时群发公众号] 警告：正式群发报错 ({str(e)})，已自动启用安全降级发布兜底防线...")
                pub_id = wechat_publisher.publish_draft(token, media_id)
                write_cron_log(f"[定时群发公众号] 成功：降级发布成功！发布ID: {pub_id}")
        else:
            write_cron_log(f"[定时群发公众号] 正在正式发布 MediaID: {media_id} (不推送) ...")
            pub_id = wechat_publisher.publish_draft(token, media_id)
            write_cron_log(f"[定时群发公众号] 成功：已正式发布！发布ID: {pub_id}")
        
        # 3. 更新状态
        data["status"] = "published"
        data["publish_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(draft_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        write_cron_log(f"[定时群发公众号] 异常崩溃：{str(e)}\n{traceback.format_exc()}")

def run_scheduled_deep_analysis(ignore_auto_run: bool = False):
    cfg = _load_config()
    da_sched = cfg.get("schedulers", {}).get("AI 深度分析", {})
    if not ignore_auto_run and not da_sched.get("auto_run", False): return
    ui_state = da_sched.get("ui_state", {})
    if not ui_state:
        write_cron_log("[AI 深度分析] 警告: 未在 config.json 中找到保存的运行配置，请先点击『保存配置并拉起定时任务』。")
        return
        
    write_cron_log("==================================================")
    write_cron_log("[AI 深度分析] 定时任务启动")
    try:
        status_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8', env=_get_exec_env())
        user_id = ""
        m = re.search(r'\{.*\}', status_res.stdout, re.DOTALL)
        if m:
            auth_data = json.loads(m.group(0))
            if auth_data.get("ok") and auth_data.get("data", {}).get("loggedIn"):
                user_id = auth_data["data"].get("userId", "")
        if not user_id:
            write_cron_log("[AI 深度分析] 错误: 知识星球未登录/未授权，任务终止。")
            return
            
        selected_group = ui_state.get("selected_group", cfg.get("selected_group", "默认群组"))
        group_id = cfg.get("user_groups", {}).get(user_id, {}).get(selected_group)
        if not group_id:
            write_cron_log(f"[AI 深度分析] 错误: 未找到选中群组 '{selected_group}' 的 ID，任务终止。")
            return
            
        scope_ui = ui_state.get("scope_ui", "最新总结 (话题+文件)")
        s_key = "all" if "最新" in scope_ui else "files"
        l_limit = ui_state.get("l_limit", 3)
        a_mode = ui_state.get("a_mode", "常规总结")
        
        write_cron_log(f"[AI 深度分析] 正在获取知识星球动态 (群组: {selected_group}, 范围: {scope_ui}, 数量: {l_limit})...")
        raw, _, _ = zsxq_client.fetch_zsxq(group_id, limit=l_limit, scope=s_key)
        if raw.startswith("获取失败") or raw.startswith("获取异常"):
            write_cron_log(f"[AI 深度分析] 知识星球数据获取失败: {raw}")
            return
        if raw.startswith("跳过分析"):
            write_cron_log(f"[AI 深度分析] 定时任务跳过: {raw}")
            return
            
        plat = cfg.get("platform", "自定义/OpenAI")
        plat_cfg = cfg.get("channel_configs", {}).get(plat, {})
        selected_model = plat_cfg.get("selected_model", "")
        
        write_cron_log(f"[AI 深度分析] 正在向大模型发起深度分析 (平台: {plat}, 模型: {selected_model}, 模式: {a_mode})...")
        res_main = llm.generate_summary(raw, plat_cfg.get("api_key"), plat_cfg.get("base_url"), selected_model, a_mode, chan_config=plat_cfg)
        if res_main.startswith("AI 总结失败") or res_main.startswith("未提供"):
            write_cron_log(f"[AI 深度分析] 分析失败: {res_main}")
            return
            
        final_res = res_main
        use_p_ui = ui_state.get("use_p_ui", False)
        cp_text = ui_state.get("cp_text", "")
        if use_p_ui and cp_text:
            write_cron_log("[AI 深度分析] 正在执行个性化二次加工...")
            final_res = llm.generate_summary(res_main, plat_cfg.get("api_key"), plat_cfg.get("base_url"), selected_model, a_mode, custom_prompt=cp_text, chan_config=plat_cfg)
            if final_res.startswith("AI 总结失败"):
                write_cron_log(f"[AI 深度分析] 二次加工失败: {final_res}")
                return
                
        use_wechat = ui_state.get("use_wechat", False)
        also_generate_report = ui_state.get("also_generate_report", False)
        
        if use_wechat:
            # 1. 前置源文本质量校验：校验 final_res 是否有效
            is_src_valid, src_reason = wechat_render.validate_wechat_article_content(final_res)
            if not is_src_valid:
                write_cron_log(f"[AI 深度分析] ⚠️ 源分析总结质量校验未通过 ({src_reason})，安全放弃微信推文生成与推送。")
                return

            wechat_orientation = ui_state.get("wechat_article_orientation", cfg.get("wechat_article_orientation", "产业宏观与行业趋势"))
            write_cron_log(f"[AI 深度分析] 🧭 推文内容定位：【{wechat_orientation}】")
            wechat_system_prompt = prompts.get_wechat_system_prompt(wechat_orientation)
            wechat_prompt = ui_state.get("wechat_prompt", "")
            wechat_user_content = f"【基础分析总结】\n{final_res}\n"
            if wechat_prompt.strip():
                wechat_user_content += f"\n【用户个性化要求】\n{wechat_prompt}"
                
            from openai import OpenAI
            client = OpenAI(api_key=plat_cfg.get("api_key"), base_url=plat_cfg.get("base_url") if plat_cfg.get("base_url") else None)
            
            raw_wechat = ""
            max_wc_attempts = 2
            for wc_attempt in range(max_wc_attempts):
                write_cron_log(f"[AI 深度分析] 正在生成微信公众号推文 (尝试 {wc_attempt+1}/{max_wc_attempts})...")
                wc_response = llm.call_chat_completion(client, selected_model, [{"role": "system", "content": wechat_system_prompt}, {"role": "user", "content": wechat_user_content}], chan_config=plat_cfg)
                if wc_response.choices and wc_response.choices[0].message.content:
                    cand_wechat = wc_response.choices[0].message.content
                    is_wc_valid, wc_reason = wechat_render.validate_wechat_article_content(cand_wechat)
                    if is_wc_valid:
                        raw_wechat = cand_wechat
                        break
                    else:
                        write_cron_log(f"[AI 深度分析] ⚠️ 微信推文安全审查未通过 ({wc_reason})，正在进行自动重试 ({wc_attempt+1}/{max_wc_attempts})...")
                        time.sleep(2)
                else:
                    write_cron_log(f"[AI 深度分析] ⚠️ 微信推文生成返回为空，正在重试 ({wc_attempt+1}/{max_wc_attempts})...")
                    time.sleep(2)

            if not raw_wechat:
                write_cron_log("[AI 深度分析] ❌ 微信推文多次重试生成均未通过安全审查或为空，已安全拦截，取消微信上传与发布！")
                return

            # 保底补全配图提示词标记并进行排版微调
            raw_wechat = image_engine.ensure_image_prompts_exist(raw_wechat)
            raw_wechat = image_engine.adjust_markdown_images_placement(raw_wechat)
            
            def replace_img(match):
                kw = match.group(1).strip()
                img_engine_str = cfg.get("image_generator", "即梦 (Dreamina)")
                if img_engine_str == "Google Gemini (Imagen 3)":
                    write_cron_log(f"[AI 深度分析] 🖼️ 正在调用 Gemini 生成配图: `{kw}`")
                    img_path = image_engine.generate_gemini_image(kw, cfg.get("google_api_key", ""), model_name=cfg.get("gemini_image_model", "imagen-4.0-generate-001"), aspect_ratio=cfg.get("image_aspect_ratio", "1:1"))
                else:
                    write_cron_log(f"[AI 深度分析] 🖼️ 正在调用即梦生成配图: `{kw}`")
                    img_path = image_engine.generate_jimeng_image(kw)
                if img_path:
                    img_path = img_path.replace("\\", "/")
                    return f"({img_path})"
                return "(https://dummyimage.com/800x400/ffebee/d32f2f.png&text=Image+Generate+Failed)"
                
            # 增强正则识别：兼容各种中括号、圆括号及冒号变体
            wechat_res = re.sub(r'\(?\[?IMAGE_GENERATE:\s*([^\]\)]+)\)?\]?', replace_img, raw_wechat)
            
            wc_filename = f"wechat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            wc_path = os.path.join(WECHAT_OUTPUT_DIR, wc_filename)
            with open(wc_path, "w", encoding="utf-8") as f:
                f.write(wechat_res)
                
            write_cron_log("[AI 深度分析] 🎨 正在使用 md2wechat 进行样式美化排版...")
            theme = ui_state.get("wechat_theme", cfg.get("wechat_theme", "spring-fresh"))
            mode_ui = ui_state.get("wechat_mode", cfg.get("wechat_mode", "AI 模式 (免费)"))
            api_key = cfg.get("md2wechat_api_key", "")
            font_size = cfg.get("wechat_font_size", "medium")
            bg_type = cfg.get("wechat_background_type", "none")
            custom_prompt = cfg.get("wechat_custom_prompt", "")
            
            html_res = wechat_render.convert_to_wechat_html(wechat_res, theme, mode_ui, api_key=api_key, font_size=font_size, bg_type=bg_type, chan_config=plat_cfg, custom_prompt=custom_prompt)
            html_filename = wc_filename.replace(".md", ".html")
            html_path = os.path.join(WECHAT_OUTPUT_DIR, html_filename)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_res)
            write_cron_log(f"[AI 深度分析] 微信推文生成成功: {html_path}")
            
            # 定时任务微信自动发布逻辑
            pub_mode = ui_state.get("wechat_publish_mode", "仅生成本地文件 (不上传)")
            if pub_mode != "仅生成本地文件 (不上传)":
                write_cron_log(f"[AI 深度分析] 触发定时微信自动发布，发布模式: {pub_mode}")
                
                accounts = wechat_publisher.load_accounts()
                selected_acc_name = ui_state.get("wechat_publish_account", "")
                active_account = next((a for a in accounts if a["name"] == selected_acc_name), None)
                if not active_account and accounts:
                    active_account = accounts[0]
                    write_cron_log(f"[AI 深度分析] 未找到指定微信账号 '{selected_acc_name}'，默认使用第一个账号 '{active_account['name']}'")
                    
                if active_account:
                    try:
                        pub_author = ui_state.get("wechat_publish_author", cfg.get("wechat_publish_author", ""))
                        pub_res = wechat_publisher.auto_publish_to_wechat(
                            wc_path, 
                            html_path, 
                            active_account, 
                            pub_mode,
                            author=pub_author
                        )
                        write_cron_log(f"[AI 深度分析] 微信自动发布成功！MediaID: {pub_res.get('media_id')}")
                        if pub_res.get("publish_id"):
                            if pub_res.get("fallback_to_publish"):
                                write_cron_log(f"[AI 深度分析] ⚠️ 微信群发超额/报错，已自动安全降级为【发布】(主页历史不可见)，ID: {pub_res.get('publish_id')}")
                            else:
                                write_cron_log(f"[AI 深度分析] 微信正式发布/群发成功！ID/PublishID: {pub_res.get('publish_id')}")
                    except Exception as pub_err:
                        write_cron_log(f"[AI 深度分析] 微信自动发布失败 (不重试): {str(pub_err)}")
                else:
                    write_cron_log("[AI 深度分析] 错误: 微信自动发布失败，未配置任何微信公众号账号")
                
        if not use_wechat or also_generate_report:
            write_cron_log("[AI 深度分析] 正在渲染专业分析报表...")
            img_p = image_engine.render_to_image(final_res, a_mode)
            write_cron_log(f"[AI 深度分析] 分析报表已生成并保存到: {img_p}")
        write_cron_log("[AI 深度分析] 定时任务执行完毕。")
    except Exception as e:
        import traceback
        write_cron_log(f"[AI 深度分析] 异常终止: {str(e)}\n{traceback.format_exc()}")

def run_scheduled_video_script(ignore_auto_run: bool = False):
    cfg = _load_config()
    vs_sched = cfg.get("schedulers", {}).get("视频脚本制作器", {})
    if not ignore_auto_run and not vs_sched.get("auto_run", False): return
    ui_state = vs_sched.get("ui_state", {})
    if not ui_state:
        write_cron_log("[视频脚本制作器] 警告: 未在 config.json 中找到保存的运行配置，请先点击『保存配置并拉起定时任务』。")
        return
        
    write_cron_log("==================================================")
    write_cron_log("[视频脚本制作器] 定时任务启动")
    try:
        plat = cfg.get("platform", "自定义/OpenAI")
        plat_cfg = cfg.get("channel_configs", {}).get(plat, {})
        selected_model = plat_cfg.get("selected_model", "")
        
        prompt_input = ui_state.get("prompt_input", "")
        virtual_history = ui_state.get("virtual_history", [])
        
        history_texts = []
        for vf in virtual_history:
            history_texts.append(f"【历史脚本（追加）：{vf['name']}】\n{vf['text']}")
        history_context = "\n\n".join(history_texts)
        
        system_prompt = "你是一个专业的金融/交易类视频脚本编导。请严格学习并模仿用户提供的历史脚本的文案风格、语气和排版格式。\n\n【重要排版指令】：请必须使用 Markdown 语法进行排版输出。为了作为提词器使用时的重音提示，请务必对文案中的核心观点、金句或转折词使用**加粗**（如 `**重点内容**`）或引用块（如 `> 核心金句`）进行高亮。"
        user_content = ""
        if history_context:
            user_content += f"以下是你需要学习参考的历史脚本序列：\n\n{history_context}\n\n====================\n\n"
        user_content += f"请为我创作一期全新的视频脚本，要求如下：\n"
        if prompt_input:
            user_content += f"\n在续写时，请必须结合以下新素材或要求：\n[新素材与要求]：\n{prompt_input}"
        else:
            user_content += "\n请注意：由于我没有提供新素材，请直接根据历史上下文的逻辑推演，自动拟定下一期主题并生成完整的视频文案！"
            
        write_cron_log(f"[视频脚本制作器] 正在向大模型发起请求 (模型: {selected_model})...")
        from openai import OpenAI
        client = OpenAI(api_key=plat_cfg.get("api_key"), base_url=plat_cfg.get("base_url") if plat_cfg.get("base_url") else None)
        response = llm.call_chat_completion(client, selected_model, [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], chan_config=plat_cfg)
        if response.choices and response.choices[0].message.content:
            script_content = response.choices[0].message.content
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = os.path.join(SCRIPT_OUTPUT_DIR, f"script_{timestamp}.md")
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            write_cron_log(f"[视频脚本制作器] 视频脚本已生成并保存到: {save_path}")
        else:
            write_cron_log("[视频脚本制作器] 错误: 大模型返回空数据。")
        write_cron_log("[视频脚本制作器] 定时任务执行完毕。")
    except Exception as e:
        import traceback
        write_cron_log(f"[视频脚本制作器] 异常终止: {str(e)}\n{traceback.format_exc()}")

def run_scheduled_indicator_docs(ignore_auto_run: bool = False):
    cfg = _load_config()
    id_sched = cfg.get("schedulers", {}).get("指标文档制作", {})
    if not ignore_auto_run and not id_sched.get("auto_run", False): return
    ui_state = id_sched.get("ui_state", {})
    if not ui_state:
        write_cron_log("[指标文档制作] 警告: 未在 config.json 中找到保存的运行配置，请先点击『保存配置并拉起定时任务』。")
        return
        
    write_cron_log("==================================================")
    write_cron_log("[指标文档制作] 定时任务启动")
    try:
        plat = cfg.get("platform", "自定义/OpenAI")
        plat_cfg = cfg.get("channel_configs", {}).get(plat, {})
        selected_model = plat_cfg.get("selected_model", "")
        
        selected_indicator = ui_state.get("selected_indicator", "")
        indicators = _load_indicators()
        if not selected_indicator or selected_indicator not in indicators:
            write_cron_log(f"[指标文档制作] 错误: 未找到选中的指标 '{selected_indicator}'，任务终止。")
            return
            
        user_content = f"【指标名称】：{selected_indicator}\n【指标源码】：\n{indicators[selected_indicator]['code']}"
        write_cron_log(f"[指标文档制作] 正在向大模型发起标准合规分析 (指标: {selected_indicator}, 模型: {selected_model})...")
        from openai import OpenAI
        client = OpenAI(api_key=plat_cfg.get("api_key"), base_url=plat_cfg.get("base_url") if plat_cfg.get("base_url") else None)
        response = llm.call_chat_completion(client, selected_model, [{"role": "system", "content": prompts.PROMPT_INDICATOR_STANDARD}, {"role": "user", "content": user_content}], chan_config=plat_cfg)
        if response.choices and response.choices[0].message.content:
            doc_content = response.choices[0].message.content
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            md_filename = f"《{selected_indicator}》---合规化_{ts}.md"
            docx_filename = f"《{selected_indicator}》---合规化_{ts}.docx"
            md_path = os.path.join(INDICATOR_DOCS_DIR, md_filename)
            docx_path = os.path.join(INDICATOR_DOCS_DIR, docx_filename)
            
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(doc_content)
            wechat_render.markdown_to_docx_file(doc_content, docx_path, indicator_name=selected_indicator)
            write_cron_log(f"[指标文档制作] 标准合规分析文档已生成并保存到: {md_path}")
        else:
            write_cron_log("[指标文档制作] 错误: 大模型返回空数据。")
        write_cron_log("[指标文档制作] 定时任务执行完毕。")
    except Exception as e:
        import traceback
        write_cron_log(f"[指标文档制作] 异常终止: {str(e)}\n{traceback.format_exc()}")

def update_scheduler():
    from apscheduler.triggers.cron import CronTrigger
    sched = get_scheduler()
    
    # 清理所有 auto_job 任务
    for job in sched.get_jobs():
        if job.id.startswith("auto_job"):
            sched.remove_job(job.id)
            
    cfg = _load_config()
    schedulers = cfg.get("schedulers", {})
    
    # 1. AI 深度分析
    da_sched = schedulers.get("AI 深度分析", {})
    if da_sched.get("auto_run", False):
        try:
            cron_expr = da_sched.get("cron_expr", "0 8 * * *")
            sched.add_job(run_scheduled_deep_analysis, CronTrigger.from_crontab(cron_expr), id="auto_job_deep_analysis")
        except Exception as e:
            pass
            
    # 2. 视频脚本制作器
    vs_sched = schedulers.get("视频脚本制作器", {})
    if vs_sched.get("auto_run", False):
        try:
            cron_expr = vs_sched.get("cron_expr", "0 8 * * *")
            sched.add_job(run_scheduled_video_script, CronTrigger.from_crontab(cron_expr), id="auto_job_video_script")
        except Exception as e:
            pass
            
    # 3. 指标文档制作
    id_sched = schedulers.get("指标文档制作", {})
    if id_sched.get("auto_run", False):
        try:
            cron_expr = id_sched.get("cron_expr", "0 8 * * *")
            sched.add_job(run_scheduled_indicator_docs, CronTrigger.from_crontab(cron_expr), id="auto_job_indicator_docs")
        except Exception as e:
            pass

    # 4. 微信公众号定时群发任务自愈重载机制
    # 移除现有 scheduler 中所有以 schedule_publish_ 开头的推文定时群发 Job，重新扫描载入
    for job in sched.get_jobs():
        if job.id.startswith("schedule_publish_"):
            try:
                sched.remove_job(job.id)
            except Exception:
                pass
                
    wechat_dir = os.path.join("outputs", "wechat")
    if os.path.exists(wechat_dir):
        import glob
        import datetime as dt_module
        draft_files = glob.glob(os.path.join(wechat_dir, "*.draft.json"))
        for draft_file in draft_files:
            try:
                with open(draft_file, "r", encoding="utf-8") as f_draft:
                    draft_data = json.load(f_draft)
                    
                if draft_data.get("status") == "scheduled":
                    media_id = draft_data.get("media_id")
                    scheduled_time_str = draft_data.get("scheduled_time")
                    
                    if media_id and scheduled_time_str:
                        scheduled_dt = dt_module.datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M:%S")
                        now_dt = dt_module.datetime.now()
                        
                        if scheduled_dt > now_dt:
                            # 目标时间在未来，重新注册
                            job_id = f"schedule_publish_{media_id}"
                            sched.add_job(
                                run_scheduled_wechat_publish,
                                'date',
                                run_date=scheduled_dt,
                                args=[os.path.abspath(draft_file)],
                                id=job_id
                            )
                            write_cron_log(f"[定时发布自愈] 成功重载任务 {job_id}，时间：{scheduled_time_str}")
                        else:
                            # 时间已过期，出于安全考虑将其重置为草稿状态并记录警告
                            draft_data["status"] = "draft"
                            with open(draft_file, "w", encoding="utf-8") as f_write:
                                json.dump(draft_data, f_write, ensure_ascii=False, indent=2)
                            write_cron_log(f"[定时发布自愈] 警告：任务已过期且未成功发布，已重置为 draft 草稿状态：{draft_file}")
                            
            except Exception as ex:
                write_cron_log(f"[定时发布自愈] 异常：载入草稿 {draft_file} 失败: {str(ex)}")

