import streamlit as st
import os
import base64
import time
import httpx
import json
import glob
import markdown
import subprocess
import fitz  # PyMuPDF
import re
from datetime import datetime
from docx import Document
from openai import OpenAI
from playwright.sync_api import sync_playwright
from apscheduler.schedulers.background import BackgroundScheduler
import sys

NPX_CMD = "npx.cmd" if sys.platform == "win32" else "npx"

# --- Config & Constants ---
IMAGE_OUTPUT_DIR = os.path.join("outputs", "images")
SCRIPT_OUTPUT_DIR = os.path.join("outputs", "scripts")
CONFIG_FILE = "config.json"
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
os.makedirs(SCRIPT_OUTPUT_DIR, exist_ok=True)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(data):
    tmp_file = CONFIG_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_file, CONFIG_FILE)

if "config" not in st.session_state:
    st.session_state.config = load_config()

config = st.session_state.config

# Default Config Setup
defaults = {
    "groups": {"默认群组": ""},
    "platform": "自定义/OpenAI",
    "mode": "常规总结",
    "selected_group": "默认群组",
    "auto_run": False,
    "run_time": "08:00",
    "channel_configs": {
        "自定义/OpenAI": {"api_key": "", "base_url": "https://api.openai.com/v1", "selected_model": "gpt-4o", "available_models": ["gpt-4o", "gpt-3.5-turbo"]},
        "火山方舟 (Volcengine)": {"api_key": "", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "selected_model": "", "available_models": []},
        "魔塔 (ModelScope)": {"api_key": "", "base_url": "https://api.modelscope.cn/v1", "selected_model": "", "available_models": []}
    },
    "custom_prompts": {"合规化处理": "请对以上内容进行合规化处理：1. 隐藏具体的人名和联系方式；2. 增加‘以上内容仅供参考，不构成投资建议’的免责声明；3. 语气调整为客观中立的中台视角。"}
}
for key, val in defaults.items():
    if key not in config:
        config[key] = val

# Migrate old config to channel_configs if necessary
if "api_key" in config and config["api_key"]:
    current_plat = config.get("platform", "自定义/OpenAI")
    if current_plat in config["channel_configs"]:
        if not config["channel_configs"][current_plat].get("api_key"):
            config["channel_configs"][current_plat]["api_key"] = config.get("api_key", "")
            config["channel_configs"][current_plat]["base_url"] = config.get("base_url", "")
            config["channel_configs"][current_plat]["selected_model"] = config.get("selected_model", "")
            config["channel_configs"][current_plat]["available_models"] = config.get("available_models", [])
            save_config(config)

if "available_models" not in st.session_state:
    st.session_state.available_models = config["channel_configs"][config.get("platform", "自定义/OpenAI")].get("available_models", [])

@st.cache_resource
def get_scheduler():
    sched = BackgroundScheduler()
    sched.start()
    return sched

if "scheduler" not in st.session_state:
    st.session_state.scheduler = get_scheduler()

if "virtual_history" not in st.session_state:
    st.session_state.virtual_history = []

def auto_run_job():
    cfg = load_config()
    if not cfg.get("auto_run", False): return
    try:
        group_id = cfg.get("groups", {}).get(cfg.get("selected_group"))
        if not group_id: return
        raw, _, _ = fetch_zsxq(group_id, limit=3, scope="all")
        if "失败" in raw or "异常" in raw: return
        
        plat = cfg.get("platform", "自定义/OpenAI")
        plat_cfg = cfg.get("channel_configs", {}).get(plat, {})
        res = generate_summary(raw, plat_cfg.get("api_key"), plat_cfg.get("base_url"), plat_cfg.get("selected_model"), cfg.get("mode", "常规总结"))
        if not res.startswith("AI 总结失败") and not res.startswith("未提供"):
            render_to_image(res, cfg.get("mode", "常规总结"))
    except: pass

def update_scheduler():
    from apscheduler.triggers.cron import CronTrigger
    sched = st.session_state.scheduler
    for job in sched.get_jobs(): sched.remove_job(job.id)
    if config.get("auto_run", False):
        try:
            cron_expr = config.get("cron_expr", "0 8 * * *")
            sched.add_job(auto_run_job, CronTrigger.from_crontab(cron_expr), id="auto_job")
        except: pass

update_scheduler()

# --- Helpers ---

def parse_uploaded_file(uploaded_file):
    if uploaded_file.name.endswith('.md'):
        return uploaded_file.getvalue().decode('utf-8')
    elif uploaded_file.name.endswith('.docx'):
        from io import BytesIO
        from docx import Document
        doc = Document(BytesIO(uploaded_file.getvalue()))
        return "\n".join([p.text for p in doc.paragraphs])
    elif uploaded_file.name.endswith('.csv'):
        import pandas as pd
        df = pd.read_csv(uploaded_file)
        return df.to_csv(index=False)
    elif uploaded_file.name.endswith('.xlsx'):
        import pandas as pd
        df = pd.read_excel(uploaded_file)
        return df.to_csv(index=False)
    return ""

def extract_text_from_pdf(content):
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        return f"[PDF 提取失败: {str(e)}]"

def fetch_zsxq(group_id, limit=3, scope="all", progress_callback=None):
    if not group_id:
        return "请提供知识星球的 Group ID。", [], []
    
    processed_files = []
    processed_topics_brief = []
    
    # 1. Auth check
    if progress_callback: progress_callback({"type": "info", "msg": "正在检查授权状态..."})
    status_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8')
    is_logged = False
    try:
        m = re.search(r'\{.*\}', status_res.stdout, re.DOTALL)
        if m:
            auth_data = json.loads(m.group(0))
            if auth_data.get("ok") and auth_data.get("data", {}).get("loggedIn"):
                is_logged = True
    except: pass
    
    if not is_logged:
        return "获取失败: 知识星球未授权。请在左侧边栏获取授权链接。", [], []

    # 2. Fetch topics
    if progress_callback: progress_callback({"type": "info", "msg": "正在向知识星球请求最新动态..."})
    # 如果是仅限附件模式，加大获取数量以供滚动筛选
    fetch_limit = max(20, limit * 3) if scope == "files" else limit
    result = subprocess.run([
        NPX_CMD, "zsxq-cli", "group", "+topics", "--group-id", str(group_id), "--limit", str(fetch_limit), "--json"
    ], capture_output=True, text=True, encoding='utf-8', timeout=30)
    
    if result.returncode != 0:
        return "获取失败: CLI 内部错误", [], []

    try:
        m = re.search(r'\{.*\}', result.stdout, re.DOTALL)
        if not m: return "获取失败: 无法解析返回数据", [], []
        
        data = json.loads(m.group(0))
        if not (data.get("success") or data.get("ok")):
            return f"获取失败: {data.get('message', '未知错误')}", [], []
        
        topics = data.get("data", {}).get("topics", []) or data.get("topics_brief", [])
        
        print("\n=== [DEBUG] 开始遍历 Topic ===")
        content_list = []
        valid_topics_count = 0
        
        for topic in topics:
            if valid_topics_count >= limit:
                break
                
            # 1. 修正提取路径：直接读取并防止 NoneType
            files_in_topic = topic.get('files') or []
            
            topic_text = ""
            if 'talk' in topic and isinstance(topic['talk'], dict): topic_text = topic['talk'].get('text', '')
            elif 'question' in topic and isinstance(topic['question'], dict): topic_text = f"提问: {topic['question'].get('text', '')}\n回答: {topic.get('answer', {}).get('text', '')}"
            elif 'article' in topic and isinstance(topic['article'], dict): topic_text = f"文章: {topic['article'].get('title', '')}"
            elif 'content' in topic: topic_text = topic.get('content', '')
            elif 'title' in topic or 'text' in topic: topic_text = topic.get('title', '') or topic.get('text', '')
            
            # 更精准的日志打印
            print(f"\n--- [DEBUG] Topic ID: {topic.get('topic_id')} ---")
            print(f"Content Preview: {topic_text[:20]}...")
            print(f"Files raw data: {str(files_in_topic)}")
            
            topic_preview = (topic_text[:20].replace('\n', ' ') + "...") if topic_text else "无正文内容"
            if progress_callback: progress_callback({"type": "topic_start", "topic_id": topic.get('topic_id'), "preview": topic_preview})
            
            if scope == "files" and not files_in_topic: 
                if progress_callback: progress_callback({"type": "topic_end", "success": False, "preview": topic_preview, "reason": "无附件"})
                continue 
            
            # 添加异常数据诊断信息
            diagnostic_info = f"TopicID: {topic.get('topic_id', 'Unknown')}, Keys: {list(topic.keys())}"
            if files_in_topic:
                diagnostic_info += f", 找到附件数量: {len(files_in_topic)}"
            else:
                diagnostic_info += ", 未找到任何附件节点"
            processed_topics_brief.append(diagnostic_info)
            
            current_content = ""
            if topic_text and topic_text != "「文件」":
                current_content += topic_text

            has_valid_file_content = False
            for f in files_in_topic:
                # 2. 兼容提取文件名属性
                fname = f.get('name') or f.get('file_name') or f.get('title') or ''
                fid = f.get('file_id') or f.get('id') or ''
                if not fid: continue
                
                # 明确剔除 MP3 等不需要的音频和富媒体
                if fname.lower().endswith(('.mp3', '.mp4', '.zip', '.rar', '.jpg', '.png')):
                    if progress_callback: progress_callback({"type": "topic_log", "msg": f"⏭️ `{fname}` 属于过滤文件，已跳过。"})
                    continue
                
                # 3. 统统保留并提取支持的文档格式
                if fname.lower().endswith(('.pdf', '.docx', '.xlsx', '.csv', '.md')):
                    if progress_callback: progress_callback({"type": "topic_log", "msg": f"⏳ 正在下载并解析附件: `{fname}` (可能需要一些时间...)"})
                    try:
                        dl_res = subprocess.run([NPX_CMD, "zsxq-cli", "api", "call", "call_zsxq_api", "--params", json.dumps({"method": "GET", "path": f"/v2/files/{fid}/download_url"})], capture_output=True, text=True, encoding='utf-8', timeout=10)
                        dl_m = re.search(r'\{.*\}', dl_res.stdout, re.DOTALL)
                        if dl_m:
                            dl_url = json.loads(dl_m.group(0)).get('download_url') or json.loads(dl_m.group(0)).get('body', {}).get('download_url')
                            if dl_url:
                                f_raw = httpx.get(dl_url, timeout=30).content
                                extracted = ""
                                if fname.lower().endswith('.pdf'):
                                    extracted = extract_text_from_pdf(f_raw)
                                elif fname.lower().endswith('.docx'):
                                    from io import BytesIO
                                    from docx import Document
                                    extracted = "\n".join([p.text for p in Document(BytesIO(f_raw)).paragraphs])
                                elif fname.lower().endswith('.xlsx'):
                                    import pandas as pd
                                    from io import BytesIO
                                    extracted = pd.read_excel(BytesIO(f_raw)).to_csv(index=False)
                                elif fname.lower().endswith('.csv'):
                                    import pandas as pd
                                    from io import BytesIO
                                    extracted = pd.read_csv(BytesIO(f_raw)).to_csv(index=False)
                                elif fname.lower().endswith('.md'):
                                    extracted = f_raw.decode('utf-8')
                                
                                if extracted.strip():
                                    current_content += f"\n[附件内容: {fname}]:\n{extracted}"
                                    processed_files.append(fname)
                                    has_valid_file_content = True
                                    if progress_callback: progress_callback({"type": "topic_log", "msg": f"✅ `{fname}` 解析成功，提取字数: {len(extracted)}"})
                                else:
                                    if progress_callback: progress_callback({"type": "topic_log", "msg": f"⚠️ `{fname}` 提取内容为空"})
                    except Exception as e:
                        if progress_callback: progress_callback({"type": "topic_log", "msg": f"❌ 解析 `{fname}` 失败: {str(e)}"})

            # 如果是“仅限附件”模式，且本条动态没有任何可以解析成功的附件，则放弃本条动态，继续寻找下一条
            if scope == "files" and not has_valid_file_content:
                if progress_callback: progress_callback({"type": "topic_end", "success": False, "preview": topic_preview, "reason": "未提取到有效附件内容"})
                continue

            if current_content.strip(): 
                content_list.append(current_content)
                valid_topics_count += 1
                if progress_callback: progress_callback({"type": "topic_end", "success": True, "preview": topic_preview})
            else:
                if progress_callback: progress_callback({"type": "topic_end", "success": False, "preview": topic_preview, "reason": "动态内容为空"})

        print("===============================\n")

        # 4. 修复 NoneType 崩溃 Bug: 在没有匹配结果时直接返回中断标识
        if not content_list:
            return "跳过分析：未找到有效文档附件", processed_files, processed_topics_brief
        return "\n\n---\n\n".join(content_list), processed_files, processed_topics_brief
        
    except Exception as e:
        return f"获取异常: {str(e)}", [], []

def generate_summary(text, api_key, base_url, model, mode, custom_prompt=None):
    if not api_key: return "未提供 API Key。"
    system_prompt = (
        "你是一个顶级金融与行业研究专家。请严格按照研报级格式输出最终成品，剔除所有 AI 味，禁止使用‘综上所述’、‘首先/其次’等呆板结构。\n"
        "【排版强制要求】\n"
        "1. 必须使用丰富的 Markdown 语法（多级标题、加粗、引用块、无序/有序列表等）构建极具结构美感的排版。\n"
        "2. 在关键数据对比、产业链剖析、多维度评估等环节，**必须大量使用 Markdown 表格**来归纳，拒绝大段纯文本堆砌。\n"
        "3. 在列举要点时，必须使用带高亮短标题的列表结构，例如：`- **核心看点**：详细解析...`。\n"
        "4. 直接输出正文，绝对不要输出“好的”、“这是报告”等任何废话。\n"
        "【内容合规与风险隔离要求（至关重要）】\n"
        "1. **弱化公司绑定与定性**：尽量以行业现象、产业链环节或群体特征来阐述，弱化或避免直接点名具体公司，绝对禁止对单个公司做出主观的定性判断或吹捧。\n"
        "2. **剔除投资暗示**：必须保持中立客观的第三方行业观察视角。绝不能出现任何带有“买入、建议建仓、看好、潜力巨大”等带有诱导性投资建议或价格预测的表述。\n"
        "3. **柔化绝对性用词**：禁止使用“一定”、“必然”、“绝对”等肯定用词，必须将其替换为“可能”、“有望”、“或将”、“呈现XX趋势”等客观柔性的学术化表述，极大降低合规风险。\n"
    )
    if mode == "个股分析": 
        system_prompt += "【当前任务】：深度个股价值分析，必须涵盖核心逻辑、业务拆解、估值及风险。重点指标必须用表格解构。"
    elif mode == "行业分析": 
        system_prompt += "【当前任务】：深度行业宏观趋势分析，涵盖宏观驱动力、产业链上下游剖析、市场竞争格局及展望。产业链和竞争格局环节必须强制使用表格排版。"
    else: 
        system_prompt += "【当前任务】：详尽总结分析，提取核心要点，将散乱的信息重构成逻辑极为清晰、带有丰富表格和加粗高亮的深度简报。"
    
    user_content = f"指令: {custom_prompt}\n\n待处理内容:\n{text}" if custom_prompt else text
    try:
        client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)
        response = client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}])
        if not response.choices:
            return f"AI 总结失败: 接口返回空数据，可能是该模型({model})暂不支持或网络限流。详情: {response}"
        return response.choices[0].message.content
    except Exception as e: return f"AI 总结失败: {str(e)}"

def render_to_image(summary_text, mode_name):
    html_content = markdown.markdown(summary_text, extensions=['tables', 'fenced_code', 'nl2br'])
    
    logo_html = ""
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="footer-logo" alt="logo">'

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&display=swap');
            :root {{ --primary: #c19b52; --brand: #1d2d50; --gold: #c19b52; --bg: #ffffff; }}
            body {{ font-family: 'Noto Sans SC', sans-serif; background: #f0f2f5; margin: 0; padding: 20px; display: flex; justify-content: center; }}
            .container {{ background: var(--bg); width: 800px; padding: 50px 60px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); position: relative; }}
            .header-banner {{ 
                background: linear-gradient(135deg, #1d2d50 0%, #2b4170 100%); 
                padding: 40px 60px 35px 60px; margin: -50px -60px 45px -60px; color: white; position: relative; border-bottom: 4px solid var(--gold);
                display: flex; justify-content: space-between; align-items: flex-end;
            }}
            .header-title {{ font-size: 34px; font-weight: 900; margin: 0; letter-spacing: 2px; color: #ffffff; text-shadow: 0 2px 10px rgba(0,0,0,0.3); }}
            .header-time {{ font-size: 14px; color: #e2e8f0; opacity: 0.9; margin-bottom: 5px; letter-spacing: 1px; font-weight: 500; }}
            
            h1 {{ font-size: 28px; color: var(--brand); margin-top: 40px; border-bottom: 2px solid #f0f0f0; padding-bottom: 15px; font-weight: 900; }}
            h2 {{ 
                font-size: 22px; color: var(--brand); margin-top: 35px; margin-bottom: 20px; 
                position: relative; padding-bottom: 10px; font-weight: 800;
            }}
            h2::after {{ content: ''; position: absolute; left: 0; bottom: 0; width: 50px; height: 4px; background: var(--gold); }}
            h3 {{ font-size: 18px; color: #333; margin-top: 25px; border-left: 5px solid var(--gold); padding-left: 15px; font-weight: 700; }}
            
            p {{ font-size: 16px; color: #353535; line-height: 1.8; margin-bottom: 18px; text-align: justify; }}
            ul, ol {{ padding-left: 20px; margin-bottom: 20px; }}
            li {{ font-size: 15.5px; color: #353535; line-height: 1.7; margin-bottom: 8px; }}
            
            table {{ width: 100%; border-collapse: collapse; margin: 25px 0; border-radius: 8px; overflow: hidden; border: 1px solid #e5e5e5; }}
            th {{ background: #f8f9fa; color: var(--brand); font-weight: 700; text-align: left; padding: 12px 15px; border-bottom: 2px solid var(--gold); }}
            td {{ padding: 12px 15px; border-bottom: 1px solid #f0f0f0; color: #353535; font-size: 14.5px; }}
            
            strong {{ color: var(--brand); font-weight: 700; }}
            .disclaimer {{ margin-top: 60px; padding: 20px; background: #f8f9fa; border-radius: 8px; font-size: 13.5px; color: #666; line-height: 1.7; border-left: 4px solid var(--gold); text-align: justify; }}
            .footer-logo {{ height: 35px; width: auto; object-fit: contain; }}
            .footer {{ margin-top: 30px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 20px; letter-spacing: 1px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-banner">
                <div class="header-title">深度分析报告</div>
                <div class="header-time">{datetime.now().strftime('%Y年%m月%d日')}</div>
            </div>
            <div class="content">{html_content}</div>
            <div class="disclaimer">
                <strong>免责声明：</strong>本文内容及数据均基于公开市场资料与行业研报，仅作逻辑梳理与行业趋势分析之用，旨在探讨投资理念与方法，不构成任何具体的投资建议或操作指引。文中提及的企业及产品仅作为产业案例分析，不构成推荐。投资有风险，入市需谨慎。请您基于自身独立判断做出决策。
            </div>
            <div class="footer">
                <div>{logo_html}</div>
                <div>DEEP SUMMARY PRO · 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </div>
    </body>
    </html>
    """
    output_path = os.path.join(IMAGE_OUTPUT_DIR, f"summary_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_template)
        page.wait_for_load_state("networkidle")
        page.locator(".container").screenshot(path=output_path)
        browser.close()
    return output_path

# --- Streamlit UI ---
st.set_page_config(page_title="AI 多功能控制台", layout="wide")

with st.sidebar:
    st.header("🧭 导航")
    page_selection = st.radio("选择功能模块", ["AI 深度分析", "视频脚本制作器"], label_visibility="collapsed")
    st.markdown("---")
    
    st.header("⚙️ 全局配置")
    st.subheader("知识星球授权")
    auth_check = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8')
    logged_in = False
    try:
        m_auth = re.search(r'\{.*\}', auth_check.stdout, re.DOTALL)
        if m_auth and json.loads(m_auth.group(0)).get("ok") and json.loads(m_auth.group(0)).get("data", {}).get("loggedIn"): logged_in = True
    except: pass
    
    if logged_in:
        st.success("✅ 已授权登录")
        if st.button("退出登录"): subprocess.run([NPX_CMD, "zsxq-cli", "auth", "logout"]); st.rerun()
    else:
        st.warning("⚠️ 未授权")
        if st.button("🔗 获取授权链接"):
            login_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "login", "--json", "--no-browser", "--no-wait"], capture_output=True, text=True, encoding='utf-8')
            try:
                m_login = re.search(r'\{.*\}', login_res.stdout, re.DOTALL)
                if m_login:
                    d_login = json.loads(m_login.group(0))["data"]
                    st.session_state.zsxq_device_code = d_login["device_code"]
                    st.markdown(f"**[👉 点击授权]({d_login['verification_uri_complete']})**")
                    st.info(f"确认码：`{d_login['user_code']}`")
            except: st.error("无法获取链接")
        if "zsxq_device_code" in st.session_state and st.button("我已完成授权"):
            with st.spinner("验证中..."):
                verify_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "login", "--device-code", st.session_state.zsxq_device_code, "--json"], capture_output=True, text=True, encoding='utf-8')
                try:
                    m_verify = re.search(r'\{.*\}', verify_res.stdout, re.DOTALL)
                    if m_verify and json.loads(m_verify.group(0)).get("ok"):
                        st.success("授权成功！")
                        del st.session_state.zsxq_device_code
                        st.rerun()
                    else:
                        st.error("未检测到成功授权，请确认您已在手机端扫码并输入了确认码！")
                except Exception:
                    st.error("验证失败：无法解析登录状态。")

    groups_dict = config["groups"]
    sel_g_name = st.selectbox("选择星球/群组", list(groups_dict.keys()), index=0 if config["selected_group"] not in groups_dict else list(groups_dict.keys()).index(config["selected_group"]))
    config["selected_group"] = sel_g_name
    curr_group_id = groups_dict[sel_g_name]
    
    with st.expander("➕ 星球管理"):
        ng_name = st.text_input("名称"); ng_id = st.text_input("Group ID")
        if st.button("保存群组") and ng_name and ng_id: config["groups"][ng_name] = ng_id; save_config(config); st.rerun()

    st.subheader("AI 配置")
    plat_ops = ["自定义/OpenAI", "火山方舟 (Volcengine)", "魔塔 (ModelScope)"]
    prev_platform = config.get("platform", "自定义/OpenAI")
    
    selected_platform = st.selectbox("AI 渠道", plat_ops, index=plat_ops.index(prev_platform) if prev_platform in plat_ops else 0)
    if selected_platform != prev_platform:
        config["platform"] = selected_platform
        save_config(config)
        st.rerun()
        
    current_chan_config = config["channel_configs"].get(selected_platform, {})
    
    new_api_key = st.text_input("API Key", value=current_chan_config.get("api_key", ""), type="password")
    new_base_url = st.text_input("Base URL", value=current_chan_config.get("base_url", ""))
    
    if new_api_key != current_chan_config.get("api_key") or new_base_url != current_chan_config.get("base_url"):
        config["channel_configs"][selected_platform]["api_key"] = new_api_key
        config["channel_configs"][selected_platform]["base_url"] = new_base_url
        save_config(config)
    
    if st.button("🔄 获取模型列表") and current_chan_config.get("api_key") and current_chan_config.get("base_url"):
        with st.spinner("获取中..."):
            try:
                h = {"Authorization": f"Bearer {current_chan_config['api_key']}"}
                r = httpx.get(f"{current_chan_config['base_url'].rstrip('/')}/models", headers=h, timeout=10)
                if r.status_code == 200:
                    models = [m["id"] for m in r.json().get("data", [])]
                    config["channel_configs"][selected_platform]["available_models"] = models
                    save_config(config)
                    st.success(f"获取成功！共获取到 {len(models)} 个可用模型。")
                else:
                    st.error(f"获取失败，HTTP 状态码: {r.status_code}")
            except Exception as e:
                st.error(f"获取异常: {str(e)}")

    all_mods = list(dict.fromkeys(current_chan_config.get("available_models", []) + config.get("manual_models", [])))
    if not all_mods: all_mods = ["gpt-4o"]
    
    new_model = st.selectbox("当前模型", all_mods, index=all_mods.index(current_chan_config.get("selected_model")) if current_chan_config.get("selected_model") in all_mods else 0)
    if new_model != current_chan_config.get("selected_model"):
        config["channel_configs"][selected_platform]["selected_model"] = new_model
        save_config(config)

    st.subheader("🤖 自动化任务 (Cron调度)")
    
    # 迁移兼容旧版的 run_time 到 cron_expr
    if "cron_expr" not in config:
        if "run_time" in config:
            try:
                hr, mn = map(int, config["run_time"].split(":"))
                config["cron_expr"] = f"{mn} {hr} * * *"
            except:
                config["cron_expr"] = "0 8 * * *"
        else:
            config["cron_expr"] = "0 8 * * *"
            
    curr_cron = config["cron_expr"]
    parts = curr_cron.split()
    c_min, c_hour, c_dow = ("0", "8", "*")
    if len(parts) >= 5:
        c_min, c_hour, c_dow = parts[0], parts[1], parts[4]
        
    try:
        r_time = datetime.strptime(f"{c_hour}:{c_min}", "%H:%M").time()
    except Exception:
        r_time = datetime.strptime("08:00", "%H:%M").time()
        
    cron_mode = st.radio("执行频率", ["每天", "按周"], index=0 if c_dow == "*" else 1, horizontal=True)
    
    wd_map = {'周一':'1', '周二':'2', '周三':'3', '周四':'4', '周五':'5', '周六':'6', '周日':'0'}
    rev_wd_map = {'1':'周一', '2':'周二', '3':'周三', '4':'周四', '5':'周五', '6':'周六', '0':'周日', '7':'周日'}
    
    selected_wds = []
    if cron_mode == "按周":
        def_wds = [rev_wd_map.get(d, '周一') for d in c_dow.split(',')] if c_dow != "*" else ["周一"]
        def_wds = list(dict.fromkeys([w for w in def_wds if w in wd_map.keys()])) # 去重并保持顺序
        selected_wds = st.multiselect("选择星期", list(wd_map.keys()), default=def_wds)
        
    new_r_time = st.time_input("执行时间", value=r_time)
    
    new_dow = "*" if cron_mode == "每天" or not selected_wds else ",".join([wd_map[w] for w in selected_wds])
    new_cron = f"{new_r_time.minute} {new_r_time.hour} * * {new_dow}"
    
    st.info(f"👉 **动态 Cron 表达式**: `{new_cron}`")
    new_auto_run = st.toggle("开启定时自动运行", value=config.get("auto_run", False))
    
    if new_cron != config.get("cron_expr") or new_auto_run != config.get("auto_run"):
        config["cron_expr"] = new_cron
        config["auto_run"] = new_auto_run
        save_config(config)
        update_scheduler()

    if st.button("💾 手动保存所有配置", use_container_width=True): save_config(config); st.success("已保存")

# Main Area
if page_selection == "AI 深度分析":
    st.title("🤖 AI 深度分析控制台")
    col1, col2 = st.columns([2, 1.3])
    with col1:
        st.subheader("📊 分析模式与数据源")
        scope_ui = st.radio("获取范围", ["最新总结 (话题+文件)", "文件总结 (仅限附件)"], horizontal=True)
        s_key = "all" if "最新" in scope_ui else "files"
        l_limit = st.number_input("获取近多少条消息", min_value=1, max_value=100, value=3)
        a_mode = st.radio("分析模式", ["常规总结", "个股分析", "行业分析"], horizontal=True)
        
        st.markdown("---")
        st.subheader("✨ 个性化输出处理")
        use_p_ui = st.checkbox("总结后进行个性化二次加工")
        cp_text = ""
        if use_p_ui:
            cp_ops = ["自定义输入"] + list(config["custom_prompts"].keys())
            sp_name = st.selectbox("选择预设", cp_ops)
            
            if sp_name == "自定义输入":
                cp_text = st.text_area("指令")
                np_name = st.text_input("预设名称")
                if st.button("💾 保存预设", use_container_width=True) and cp_text and np_name: 
                    config["custom_prompts"][np_name] = cp_text
                    save_config(config)
                    st.rerun()
            else:
                cp_text = st.text_area("编辑指令", value=config["custom_prompts"][sp_name], height=120)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🔄 更新当前预设", use_container_width=True):
                        config["custom_prompts"][sp_name] = cp_text
                        save_config(config)
                        st.success("更新成功！")
                        time.sleep(1)
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ 删除当前预设", use_container_width=True):
                        st.session_state['delete_confirm'] = sp_name
                
                if st.session_state.get('delete_confirm') == sp_name:
                    with st.container(border=True):
                        st.warning(f"⚠️ 确定要删除预设【{sp_name}】吗？")
                        del_col1, del_col2 = st.columns(2)
                        if del_col1.button("✅ 确认删除", type="primary", use_container_width=True):
                            del config["custom_prompts"][sp_name]
                            save_config(config)
                            del st.session_state['delete_confirm']
                            st.rerun()
                        if del_col2.button("❌ 取消", use_container_width=True):
                            del st.session_state['delete_confirm']
                            st.rerun()

        if st.button("🚀 立即开始深度分析", use_container_width=True, type="primary"):
            if not current_chan_config.get("api_key"):
                st.error("请先在左侧全局配置中填写 API Key！")
                st.stop()
                
            log_container = st.container()
            with log_container:
                st.write("### 🔄 任务执行日志")
                with st.status("🚀 深度分析任务执行中...", expanded=True) as main_status:
                    
                    def update_progress(event):
                        if event['type'] == 'info':
                            main_status.write(f"ℹ️ {event['msg']}")
                        elif event['type'] == 'topic_start':
                            main_status.write(f"⏳ **处理话题**: `{event['preview']}`")
                        elif event['type'] == 'topic_log':
                            main_status.write(f"　 └─ {event['msg']}")
                        elif event['type'] == 'topic_end':
                            if event.get('success'):
                                main_status.write(f"　 └─ ✅ **完成**")
                            else:
                                reason = event.get('reason', '')
                                main_status.write(f"　 └─ ⏭️ **跳过** ({reason})")
                    
                    raw, f_list, briefs = fetch_zsxq(curr_group_id, limit=l_limit, scope=s_key, progress_callback=update_progress)
                    
                    if "失败" in raw or "异常" in raw or "跳过" in raw or (not briefs and not f_list):
                        main_status.update(label="任务异常终止", state="error")
                        st.error(f"分析无法继续: {raw}")
                        st.stop()

                    main_status.write(f"🧠 **向大模型发起请求** (模型: `{current_chan_config.get('selected_model')}`)...")
                    main_status.write("　 └─ 正在构建上下文 Prompt...")
                    res_main = generate_summary(raw, current_chan_config.get("api_key"), current_chan_config.get("base_url"), current_chan_config.get("selected_model"), a_mode)
                    
                    if res_main.startswith("AI 总结失败") or res_main.startswith("未提供"):
                        main_status.update(label="任务异常终止", state="error")
                        st.error(res_main)
                        st.stop()

                    final_res = res_main
                    if use_p_ui and cp_text:
                        main_status.write("✨ **正在执行个性化二次美化加工**...")
                        final_res = generate_summary(res_main, current_chan_config.get("api_key"), current_chan_config.get("base_url"), current_chan_config.get("selected_model"), a_mode, custom_prompt=cp_text)
                        if final_res.startswith("AI 总结失败"):
                            main_status.update(label="二次美化加工异常", state="error")
                            st.error(final_res)
                            st.stop()
                            
                    main_status.write("🎨 正在渲染专业分析报表...")
                    main_status.update(label="🎉 AI 深度分析完成！", state="complete", expanded=False)

            img_p = render_to_image(final_res, a_mode)
            st.session_state['latest_img'] = img_p
            st.success("报表已生成！请在右侧预览。")
            time.sleep(1)
            st.rerun()

    with col2:
        st.subheader("🖼️ 报告预览")
        if 'latest_img' in st.session_state and os.path.exists(st.session_state['latest_img']):
            st.image(st.session_state['latest_img'], use_container_width=True)
        
        st.write("---")
        st.subheader("📅 历史报告归档")
        hist_imgs = sorted(glob.glob(os.path.join(IMAGE_OUTPUT_DIR, "*.png")), reverse=True)
        if not hist_imgs: st.info("暂无历史记录")
        else:
            d_groups = {}
            for h_im in hist_imgs:
                try:
                    ds = os.path.basename(h_im).split('_')[1][:8]
                    dfmt = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
                except: dfmt = "其他"
                if dfmt not in d_groups: d_groups[dfmt] = []
                d_groups[dfmt].append(h_im)
            
            for d_key, d_ims in d_groups.items():
                with st.expander(f"📅 {d_key} ({len(d_ims)}份)"):
                    for single_im in d_ims:
                        st.image(single_im, caption=os.path.basename(single_im))

elif page_selection == "视频脚本制作器":
    st.title("🎥 视频脚本制作器")
    
    col1, col2 = st.columns([2, 1.3])
    with col1:
        st.subheader("📁 历史脚本库 (供AI学习风格/续写)")
        uploaded_files = st.file_uploader("支持多文件上传 (.docx, .md, .xlsx, .csv)", type=['docx', 'md', 'xlsx', 'csv'], accept_multiple_files=True)
        
        if st.session_state.virtual_history:
            st.markdown("**📌 已追加的虚拟历史脚本:**")
            for vf in st.session_state.virtual_history:
                st.write(f"📄 `{vf['name']}`")
            if st.button("🗑️ 清空虚拟历史"):
                st.session_state.virtual_history = []
                st.rerun()
        
        st.markdown("---")
        st.subheader("⚙️ 生成设置")
        script_mode = st.radio("生成模式", ["仿写现有格式生成新脚本", "根据历史序列向后发散续写（例如基于0,1,2,3,4续写5,6）"], horizontal=False)
        export_format = st.selectbox("导出格式", [".docx", ".md"])
        
        st.markdown("---")
        st.subheader("📝 素材与提示词")
        prompt_input = st.text_area("输入新的核心观点、素材内容或具体要求...", height=150, placeholder="例如：今天我们来讲一下人工智能在医疗领域的最新应用，重点突出AI辅助诊断的高效性...")
        
        if st.button("🚀 开始生成脚本", use_container_width=True, type="primary"):
            if not current_chan_config.get("api_key"):
                st.error("请先在左侧全局配置中填写 API Key！")
                st.stop()
                
            with st.status("正在启动脚本制作流程...", expanded=True) as status:
                st.write("🔍 分析历史脚本与素材...")
                
                history_texts = []
                for f in uploaded_files:
                    txt = parse_uploaded_file(f)
                    if txt: history_texts.append(f"【历史脚本：{f.name}】\n{txt}")
                for vf in st.session_state.virtual_history:
                    history_texts.append(f"【历史脚本（追加）：{vf['name']}】\n{vf['text']}")
                history_context = "\n\n".join(history_texts)
                
                system_prompt = "你是一个专业的金融/交易类视频脚本编导。请严格学习并模仿用户提供的历史脚本的文案风格、语气（如口语化、设问式）和排版格式。\n\n【重要排版指令】：请必须使用 Markdown 语法进行排版输出。为了作为提词器使用时的重音提示，请务必对文案中的核心观点、金句或转折词使用**加粗**（如 `**重点内容**`）或引用块（如 `> 核心金句`）进行高亮。"
                
                user_content = ""
                if history_context:
                    user_content += f"以下是你需要学习参考的历史脚本序列：\n\n{history_context}\n\n====================\n\n"
                
                if "仿写" in script_mode:
                    user_content += f"请根据以上提供的历史脚本风格（如果没有历史脚本，请自行发挥专业的金融编导水平），结合以下新素材，仿写生成一篇全新的视频脚本：\n\n[新素材与要求]：\n{prompt_input}"
                else:
                    user_content += f"请分析前面提供的历史脚本序列的故事线、知识递进逻辑和表达手法，自动推理并顺延生成最新一期的视频脚本。要求保持一贯的口语化、设问式风格，并结合以下新素材：\n\n[新素材与要求]：\n{prompt_input}"
                
                st.write(f"🧠 AI 正在构思与生成 (模型: {current_chan_config.get('selected_model')})...")
                
                try:
                    client = OpenAI(api_key=current_chan_config.get("api_key"), base_url=current_chan_config.get("base_url") if current_chan_config.get("base_url") else None)
                    response = client.chat.completions.create(
                        model=current_chan_config.get("selected_model"),
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}
                        ]
                    )
                    if not response.choices:
                        raise Exception(f"接口返回空数据，可能是该模型暂不支持或网络限流。详情: {response}")
                    script_content = response.choices[0].message.content
                    st.session_state['generated_script_preview'] = script_content
                    st.session_state['export_format_choice'] = export_format
                    
                    # 保存到历史归档
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    save_path = os.path.join(SCRIPT_OUTPUT_DIR, f"script_{timestamp}.md")
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(script_content)
                        
                    status.update(label="脚本生成完成！", state="complete", expanded=False)
                    st.success("生成成功！请在右侧预览并下载。")
                except Exception as e:
                    status.update(label="任务异常终止", state="error")
                    st.error(f"脚本生成失败: {str(e)}")

    with col2:
        st.subheader("📺 生成结果预览")
        
        preview_text = st.session_state.get('generated_script_preview', '')
        if preview_text:
            styled_html = f"""
            <style>
                .script-preview-container {{
                    font-size: 16px;
                    line-height: 1.8;
                    color: #333;
                }}
                .script-preview-container strong {{
                    color: #d97706; /* 深橙色/主题色 */
                    font-weight: 900;
                    background-color: #fef3c7;
                    padding: 0 4px;
                    border-radius: 3px;
                }}
                .script-preview-container blockquote {{
                    border-left: 5px solid #07c160; /* 主题绿 */
                    padding: 12px 15px;
                    margin: 15px 0;
                    color: #4b5563;
                    background-color: #f9fafb;
                    border-radius: 0 8px 8px 0;
                    font-style: italic;
                }}
            </style>
            """
            st.markdown(styled_html, unsafe_allow_html=True)
            
            with st.container(border=True):
                st.markdown(f'<div class="script-preview-container">{markdown.markdown(preview_text, extensions=["extra", "nl2br"])}</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            st.subheader("💾 导出与下载")
            
            # Real download logic for generated scripts
            ext = st.session_state.get('export_format_choice', '.md')
            file_name = f"视频脚本_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
            
            if ext == ".docx":
                from io import BytesIO
                from docx import Document
                from docx.shared import RGBColor
                from docx.enum.text import WD_COLOR_INDEX
                import re
                
                doc = Document()
                for line in preview_text.split('\n'):
                    line = line.strip()
                    if not line:
                        doc.add_paragraph()
                        continue
                    
                    if line.startswith('### '):
                        doc.add_heading(line[4:], level=3)
                        continue
                    elif line.startswith('## '):
                        doc.add_heading(line[3:], level=2)
                        continue
                    elif line.startswith('# '):
                        doc.add_heading(line[2:], level=1)
                        continue
                    
                    is_quote = line.startswith('> ')
                    is_bullet = line.startswith('- ') or line.startswith('* ')
                    
                    if is_bullet:
                        p = doc.add_paragraph(style='List Bullet')
                        text = line[2:]
                    else:
                        p = doc.add_paragraph()
                        text = line[2:] if is_quote else line
                        
                    # 解析并映射加粗与颜色
                    parts = re.split(r'(\*\*.*?\*\*)', text)
                    for part in parts:
                        if part.startswith('**') and part.endswith('**'):
                            run = p.add_run(part[2:-2])
                            run.bold = True
                            run.font.color.rgb = RGBColor(217, 119, 6) # 对应 CSS 的深橙色 #d97706
                            run.font.highlight_color = WD_COLOR_INDEX.YELLOW # 黄色背景高亮
                        elif part:
                            run = p.add_run(part)
                            if is_quote:
                                run.font.color.rgb = RGBColor(7, 193, 96) # 对应 CSS 的主题绿 #07c160
                                run.italic = True
                                
                bio = BytesIO()
                doc.save(bio)
                file_data = bio.getvalue()
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                file_data = preview_text.encode('utf-8')
                mime_type = "text/plain"
            
            st.download_button(
                label=f"⬇️ 下载 {ext} 文件",
                data=file_data,
                file_name=file_name,
                mime=mime_type,
                use_container_width=True
            )
            
            st.markdown("---")
            if st.button("➕ 将此篇加入参考库，继续生成下一期", use_container_width=True):
                next_index = len(st.session_state.virtual_history) + 1
                v_name = f"新生成_追加_{next_index}.md"
                st.session_state.virtual_history.append({"name": v_name, "text": preview_text})
                st.success(f"已成功加入左侧参考库：{v_name}")
                time.sleep(1)
                st.rerun()
        else:
            st.info("暂无生成内容，请先在左侧输入素材并点击开始生成。")
            
        st.write("---")
        st.subheader("📅 历史生成归档")
        hist_scripts = sorted(glob.glob(os.path.join(SCRIPT_OUTPUT_DIR, "*.md")), reverse=True)
        if not hist_scripts:
            st.info("暂无历史记录")
        else:
            d_groups = {}
            for h_sc in hist_scripts:
                try:
                    ds = os.path.basename(h_sc).split('_')[1]
                    dfmt = f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
                except:
                    dfmt = "其他"
                if dfmt not in d_groups: d_groups[dfmt] = []
                d_groups[dfmt].append(h_sc)
            
            for d_key, d_scs in d_groups.items():
                with st.expander(f"📅 {d_key} ({len(d_scs)}份)"):
                    for single_sc in d_scs:
                        sc_name = os.path.basename(single_sc)
                        if st.button(f"📄 {sc_name}", key=f"hist_{single_sc}"):
                            with open(single_sc, "r", encoding="utf-8") as f:
                                st.session_state['generated_script_preview'] = f.read()
                            st.session_state['export_format_choice'] = '.md'
                            st.rerun()
