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
INDICATOR_DOCS_DIR = os.path.join("outputs", "indicator_docs")
CONFIG_FILE = "config.json"
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)
os.makedirs(SCRIPT_OUTPUT_DIR, exist_ok=True)
os.makedirs(INDICATOR_DOCS_DIR, exist_ok=True)

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

INDICATORS_FILE = "indicators.json"

PROMPT_INDICATOR_STANDARD = """你是一个顶级金融技术分析专家，请根据提供的指标源码，严格按照以下结构输出技术观察文档：

【绝对红线：禁止金融预测与违规交易指令】
你的生成内容必须 100% 合规。严禁出现任何具有明确方向预测、交易暗示或主观情绪的词汇。
1. **违禁词库（绝对不可使用）**：抄底、逃顶、建仓、满仓、空仓、加仓、减仓、买入、卖出、暴涨、暴跌、必涨、必跌、主力、庄家、洗盘、拉升、砸盘、黑马、牛股、底部确立。
2. **强制替换规则**：
   - 将所有带有方向色彩的词替换为中立词汇，例如："抄底" -> "低位关注" 或 "潜在企稳"；"逃顶" -> "高位风险"；"买入/卖出" -> "信号触发/条件满足"；"趋势线<11" 只能表述为 "进入低位观察区"。
3. **安全缓冲用语**：所有描述必须加上“可能”、“潜在”、“或将”、“观察”等缓冲词，必须明确强调指标只是历史数据的概率统计，不构成对未来确定性的预测。

【绝对红线：禁止暴露代码规则（面向小白）】
用户是没有任何编程基础的金融小白，他们在使用软件时只能看到最终的指标图形（如：红绿柱体、黄白曲线、买卖文字提示），绝对看不到底层的代码逻辑。
1. **禁止暴露代码**：绝对禁止在文档中出现任何原始代码段、函数名（如 FILTER、CROSS、EMA、SMA）、代码变量名（如 C、H、L、O）或计算公式。
2. **强制图形化翻译**：必须将所有代码逻辑全部翻译为“盘面图形的视觉表现大白话”。例如：
   - 错误：“C上穿均线” / 正确：“当K线实体向上突破参考线”
   - 错误：“FILTER(...,15)” / 正确：“信号触发后会进行一段时间的观察，过滤掉频繁闪烁的无效信号”
   - 错误：“最低价+波动幅度*0.5” / 正确：“基于近期波动幅度测算的低位参考线”
   - 错误：“元素：`支撑`” / 正确：“元素：底部参考线”

【强制输出排版与色彩规范】
1. 必须使用 Markdown 层级（## 二级标题、### 三级标题）。核心结论必须使用 `>` 引用块（以总结性的大白话呈现）。
2. 绝对禁止在全文中使用任何 Emoji 表情符号（坚决删除所有 Emoji）。
3. **强制色彩标注（系统会做拦截处理，请严格按此格式写）**：
   - 遇到【风险、顶部、空头、压力、预警、超买】等词汇，必须使用 `:green[词汇]` 或 `:orange[词汇]` 进行包裹。
   - 遇到【底部、多头、支撑、低位、企稳、机会】等词汇，必须使用 `:red[词汇]` 进行包裹。
   - 强调性的核心逻辑或公式、重要参数，请直接使用纯文字或 **加粗**。
   - ⚠️ 警告：千万不要把色彩标签和加粗标签嵌套使用（绝不能写 `**:red[词汇]**` 或 `:red[**词汇**]`），色彩标签必须独立使用！且冒号必须是半角英文字符！
4. **面向小白用户**：内容必须尽量通俗易懂，结论前置，然后再用大白话补充解释原因。

【强制输出章节】
## 一、指标定位
## 二、盘面视觉与核心逻辑
## 三、合规化技术观察标签解读
## 四、信号解析与实战观察流程
## 五、特别教学与重要风险提示"""

PROMPT_INDICATOR_COMMUNITY = """你现在是一位幽默、接地气且拥有多年实盘经验的资深交易技术讲师，主要面向社群用户互动。
请根据以下标准技术文档，将其转化为高互动的社群语境教学文档：

【绝对红线：禁止金融预测与违规交易指令】
你的生成内容必须 100% 合规。严禁出现任何具有明确方向预测、交易暗示或主观情绪的词汇。
1. **违禁词库（绝对不可使用）**：抄底、逃顶、建仓、满仓、空仓、加仓、减仓、买入、卖出、暴涨、暴跌、必涨、必跌、主力、庄家、洗盘、拉升、砸盘、黑马、牛股、底部确立。
2. **强制替换规则**：
   - 将所有带有方向色彩的词替换为中立词汇，例如："抄底" -> "低位关注" 或 "潜在企稳"；"逃顶" -> "高位风险"；"买入/卖出" -> "信号触发/条件满足"。
3. **安全缓冲用语**：所有描述必须加上“可能”、“潜在”、“或将”、“观察”等缓冲词，必须明确强调指标只是历史数据的概率统计，不构成对未来确定性的预测。

【绝对红线：禁止暴露代码规则（面向小白）】
用户是没有任何编程基础的金融小白，他们在使用软件时只能看到最终的指标图形（如：红绿柱体、黄白曲线、买卖文字提示），绝对看不到底层的代码逻辑。
1. **禁止暴露代码**：绝对禁止在文档中出现任何原始代码段、函数名（如 FILTER、CROSS、EMA、SMA）、代码变量名（如 C、H、L、O）或计算公式。
2. **强制图形化翻译**：必须将所有代码逻辑全部翻译为“盘面图形的视觉表现大白话”。例如：不要写“C上穿均线”，要写“当K线实体向上突破参考线”；不要写“FILTER(...,15)”，要写“系统过滤掉了频繁闪烁的无效信号”。

【强制输出排版与色彩规范】
1. 必须保留 Markdown 层级标题。核心心法必须使用 `>` 引用块（以总结性的大白话呈现）。
2. 绝对禁止在全文中使用任何 Emoji 表情符号（坚决删除所有 Emoji）。
3. **强制色彩标注（系统会做拦截处理，请严格按此格式写）**：
   - 负面/预警类（顶部/空头/压力）：必须使用 `:green[词汇]` 或 `:orange[词汇]`。
   - 正面/机会类（底部/多头/支撑）：必须使用 `:red[词汇]`。
   - 强调核心逻辑、公式使用纯文字或 **加粗**。
   - ⚠️ 警告：千万不要把色彩标签和加粗标签嵌套使用！且冒号必须是半角英文字符！
4. **面向小白用户**：通俗易懂，结论前置，然后再用大白话补充解释原因。

【内容结构指令】
1. 引导语：以散户常见的技术观察盲区产生共鸣作为开头。
2. 话题互动：设置一个轻互动话题，引导客观复盘。
3. 知识讲解：采用《指标小课堂》系列形式（如标明：第1期），结合盘面图形表现，深入浅出讲解。
4. **必须生成表格**：生成一个名为“进阶形态与风控应对预案”的 Markdown 表格，严格包含三列：`| 盘面图形特征 | 技术观察含义 | 合规化应对策略建议 |`。
5. 结尾：发起学习打卡或客观技术小结任务，鼓励大家留言互动。"""

def load_indicators():
    if os.path.exists(INDICATORS_FILE):
        try:
            with open(INDICATORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_indicator(name, code):
    data = load_indicators()
    data[name] = {
        "code": code,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    tmp_file = INDICATORS_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp_file, INDICATORS_FILE)

def delete_indicator(name):
    data = load_indicators()
    if name in data:
        del data[name]
        tmp_file = INDICATORS_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_file, INDICATORS_FILE)

if "config" not in st.session_state:
    st.session_state.config = load_config()

config = st.session_state.config

def markdown_to_docx_file(md_text, filepath, indicator_name="本指标"):
    from docx import Document
    from docx.shared import RGBColor, Pt
    from docx.oxml.shared import OxmlElement
    from docx.oxml.ns import qn
    import re
    
    # 标题颜色分级体系
    HEADING_COLORS = {
        1: RGBColor(0, 63, 114),    # 深靛蓝 — 一级标题
        2: RGBColor(0, 82, 148),    # 靛蓝 — 二级标题
        3: RGBColor(34, 107, 156),  # 钢蓝 — 三级标题
    }
    
    doc = Document()
    lines = md_text.split('\n')
    
    in_table = False
    table = None
    in_code_block = False
    prev_was_blank = False
    
    def _render_inline(p, text, is_quote=False, is_th=False):
        # 清洗可能存在的全角冒号及嵌套加粗
        text = text.replace("：green[", ":green[").replace("：red[", ":red[").replace("：orange[", ":orange[")
        # 脱掉颜色标签外层的加粗标记 (例如 **:red[升]** -> :red[升])
        text = re.sub(r'\*\*\s*(:(?:green|red|orange)\[.*?\])\s*\*\*', r'\1', text)
        
        pattern = r'(:(?:green|red|orange)\[.*?\]|\*\*.*?\*\*)'
        parts = re.split(pattern, text)
        for part in parts:
            if not part: continue
            run = p.add_run()
            if is_quote:
                run.bold = True
                run.font.color.rgb = RGBColor(64, 64, 64)
            
            if is_th: run.bold = True
                
            if part.startswith(':green[') and part.endswith(']'):
                run.text = part[7:-1]
                run.font.color.rgb = RGBColor(0, 128, 0)
                run.bold = True
            elif part.startswith(':red[') and part.endswith(']'):
                run.text = part[5:-1]
                run.font.color.rgb = RGBColor(255, 0, 0)
                run.bold = True
            elif part.startswith(':orange[') and part.endswith(']'):
                run.text = part[8:-1]
                run.font.color.rgb = RGBColor(255, 165, 0)
                run.bold = True
            elif part.startswith('**') and part.endswith('**'):
                run.text = part[2:-2]
                run.bold = True
            else:
                run.text = part
                
    def _set_heading_color(h, level):
        color = HEADING_COLORS.get(level, RGBColor(0, 82, 148))
        for run in h.runs:
            run.font.color.rgb = color
            run.bold = True
                
    for line in lines:
        stripped = line.strip()
        
        # 处理代码块标记
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            prev_was_blank = False
            continue
        
        # 代码块内容：等宽缩进段落
        if in_code_block:
            p = doc.add_paragraph()
            run = p.add_run(line.rstrip())
            run.font.name = 'Consolas'
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(80, 80, 80)
            pf = p.paragraph_format
            pf.left_indent = Pt(24)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            prev_was_blank = False
            continue
        
        # 过滤水平分隔线 --- / *** / ___
        if re.match(r'^[-*_]{3,}$', stripped):
            prev_was_blank = False
            continue
        
        # 空行处理：直接跳过，避免生成无意义的大缝隙空行
        if not stripped:
            if in_table:
                in_table = False
            continue
        
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if not in_table:
                in_table = True
                table = doc.add_table(rows=1, cols=len(cells))
                table.style = 'Table Grid'
                row_cells = table.rows[0].cells
                for i, cell_text in enumerate(cells):
                    if i < len(row_cells): _render_inline(row_cells[i].paragraphs[0], cell_text, is_th=True)
            else:
                if all(re.match(r'^[-:\s]+$', c) for c in cells): continue 
                row_cells = table.add_row().cells
                for i, cell_text in enumerate(cells):
                    if i < len(row_cells): _render_inline(row_cells[i].paragraphs[0], cell_text)
            continue
        else:
            if in_table: in_table = False
        
        if stripped.startswith('#### '):
            h = doc.add_heading(level=4)
            _render_inline(h, stripped[5:])
            _set_heading_color(h, 3)
        elif stripped.startswith('### '): 
            h = doc.add_heading(level=3)
            _render_inline(h, stripped[4:])
            _set_heading_color(h, 3)
        elif stripped.startswith('## '): 
            h = doc.add_heading(level=2)
            _render_inline(h, stripped[3:])
            _set_heading_color(h, 2)
        elif stripped.startswith('# '): 
            h = doc.add_heading(level=1)
            _render_inline(h, stripped[2:])
            _set_heading_color(h, 1)
        else:
            is_quote = stripped.startswith('>')
            is_bullet = stripped.startswith('- ') or stripped.startswith('* ')
            if is_bullet:
                p = doc.add_paragraph(style='List Bullet')
                text = stripped[2:]
            else:
                p = doc.add_paragraph()
                if is_quote:
                    text = stripped[1:].strip()
                else:
                    text = stripped
            if text:
                _render_inline(p, text, is_quote)

    # 动态追加美化版的合规免责声明（与指标名称绑定）
    doc.add_paragraph()
    dtbl = doc.add_table(rows=1, cols=1)
    dcell = dtbl.cell(0, 0)
    
    tcPr = dcell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'FFF0F0')
    tcPr.append(shd)
    
    tcBorders = OxmlElement('w:tcBorders')
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single')
    left.set(qn('w:sz'), '24')
    left.set(qn('w:space'), '0')
    left.set(qn('w:color'), 'C00000')
    tcBorders.append(left)
    for border_name in ['top', 'right', 'bottom']:
        b = OxmlElement(f'w:{border_name}')
        b.set(qn('w:val'), 'nil')
        tcBorders.append(b)
    tcPr.append(tcBorders)

    dp1 = dcell.paragraphs[0]
    r1 = dp1.add_run("重要合规化声明：\n")
    r1.bold = True
    r1.font.color.rgb = RGBColor(192, 0, 0)
    
    dp2 = dcell.add_paragraph()
    r2 = dp2.add_run(f"以上关于《{indicator_name}》的所有信号提示和区间标注，均是基于历史收盘价等统计数据的技术测算展示，不保证任何未来走势预测的准确性。\n\n")
    r2.font.color.rgb = RGBColor(192, 0, 0)
    
    r3 = dp2.add_run(f"本手册中涉及的所有技术观察标签和计算逻辑仅供技术分析学习与参考，不构成任何形式的投资建议或操作指令。投资者据此操作风险自担，市场有风险，投资需谨慎。请务必结合自身风险承受能力，严格执行止盈止损纪律，独立做出判断。")
    r3.font.color.rgb = RGBColor(192, 0, 0)

    doc.save(filepath)

def get_bing_image(keyword):
    import httpx
    import re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    url = f"https://cn.bing.com/images/search?q={keyword}&first=1"
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        matches = re.findall(r'murl&quot;:&quot;(http[^&]+)&quot;', resp.text)
        if matches:
            return matches[0]
    except Exception:
        pass
    return f"https://picsum.photos/seed/{keyword}/800/400"

def markdown_to_wechat_docx_bytes(md_text):
    from docx import Document
    from docx.shared import RGBColor, Pt, Inches
    from io import BytesIO
    import re
    import httpx

    doc = Document()
    lines = md_text.split('\n')
    
    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        
        # 匹配图片 ![alt](url)
        img_match = re.search(r'!\[.*?\]\((https?://.*?)\)', stripped)
        if img_match:
            img_url = img_match.group(1)
            try:
                resp = httpx.get(img_url, timeout=15)
                if resp.status_code == 200:
                    doc.add_picture(BytesIO(resp.content), width=Inches(6.0))
            except Exception:
                pass
            continue
            
        if stripped.startswith('#'):
            level = len(stripped.split(' ')[0])
            h = doc.add_heading(level=level)
            h.add_run(stripped[level:].strip())
        elif stripped.startswith('>'):
            p = doc.add_paragraph()
            r = p.add_run(stripped[1:].strip())
            r.font.color.rgb = RGBColor(100, 100, 100)
            r.bold = True
        else:
            p = doc.add_paragraph()
            # 简单处理加粗
            parts = re.split(r'(\*\*.*?\*\*)', stripped)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    r = p.add_run(part[2:-2])
                    r.bold = True
                else:
                    p.add_run(part)

    out = BytesIO()
    doc.save(out)
    return out.getvalue()

# Default Config Setup
defaults = {
    "user_groups": {},
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
        # Resolve group_id based on current CLI login
        status_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8')
        user_id = ""
        m = re.search(r'\{.*\}', status_res.stdout, re.DOTALL)
        if m:
            auth_data = json.loads(m.group(0))
            if auth_data.get("ok") and auth_data.get("data", {}).get("loggedIn"):
                user_id = auth_data["data"].get("userId", "")
        
        if not user_id: return
        group_id = cfg.get("user_groups", {}).get(user_id, {}).get(cfg.get("selected_group"))
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
        err_msg = result.stderr.strip() if result.stderr else (result.stdout.strip() if result.stdout else "CLI 内部错误")
        m_err = re.search(r'(error:.*?)(?:\r|\n|$)', err_msg)
        if m_err: err_msg = m_err.group(1)
        return f"获取失败: {err_msg}", [], []

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
            
            if scope == "files":
                has_potential = False
                for f in files_in_topic:
                    fname = f.get('name') or f.get('file_name') or f.get('title') or ''
                    if fname.lower().endswith(('.pdf', '.docx', '.xlsx', '.csv', '.md')):
                        has_potential = True
                        break
                if not has_potential:
                    continue
                    
            if progress_callback: progress_callback({"type": "topic_start", "topic_id": topic.get('topic_id'), "preview": topic_preview})
            
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
    page_selection = st.radio("选择功能模块", ["AI 深度分析", "视频脚本制作器", "指标文档制作"], label_visibility="collapsed")
    st.markdown("---")
    
    st.header("⚙️ 全局配置")
    st.subheader("知识星球授权")
    auth_check = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8')
    logged_in = False
    user_id = ""
    user_name = ""
    try:
        m_auth = re.search(r'\{.*\}', auth_check.stdout, re.DOTALL)
        if m_auth:
            auth_data = json.loads(m_auth.group(0))
            if auth_data.get("ok") and auth_data.get("data", {}).get("loggedIn"):
                logged_in = True
                user_id = auth_data["data"].get("userId", "")
                user_name = auth_data["data"].get("userName", "")
    except: pass
    
    if logged_in:
        st.success(f"✅ {user_name} (已授权)")
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

    # Dynamic groups based on userId
    if logged_in and user_id:
        if "user_groups" not in config: config["user_groups"] = {}
        if user_id not in config["user_groups"]:
            # Initialize with old groups if present, otherwise default
            config["user_groups"][user_id] = config.get("groups", {"默认群组": ""})
            save_config(config)
        groups_dict = config["user_groups"][user_id]
    else:
        groups_dict = {"默认群组": ""}
        
    group_keys = list(groups_dict.keys())
    if not group_keys:
        groups_dict = {"默认群组": ""}
        group_keys = ["默认群组"]
        
    # Maintain selected_group consistency
    if config.get("selected_group") not in group_keys:
        config["selected_group"] = group_keys[0]

    sel_g_name = st.selectbox("选择星球/群组", group_keys, index=group_keys.index(config["selected_group"]))
    if sel_g_name != config["selected_group"]:
        config["selected_group"] = sel_g_name
        save_config(config)
        
    curr_group_id = groups_dict[sel_g_name]
    
    if logged_in and user_id:
        with st.expander("➕ 星球管理"):
            st.markdown("**新增或修改群组**")
            ng_name = st.text_input("星球名称", placeholder="例如：阿铭linux")
            ng_id = st.text_input("Group ID", placeholder="星球数字ID")
            if st.button("💾 保存/更新群组"):
                if ng_name and ng_id:
                    config["user_groups"][user_id][ng_name] = ng_id
                    config["selected_group"] = ng_name
                    save_config(config)
                    st.success("更新成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("名称和ID不能为空！")
                    
            st.markdown("---")
            st.markdown("**删除群组**")
            del_g_name = st.selectbox("选择要删除的群组", group_keys)
            if st.button("🗑️ 删除选中群组"):
                if del_g_name in config["user_groups"][user_id]:
                    del config["user_groups"][user_id][del_g_name]
                    if config["selected_group"] == del_g_name:
                        config["selected_group"] = list(config["user_groups"][user_id].keys())[0] if config["user_groups"][user_id] else ""
                    save_config(config)
                    st.success("删除成功！")
                    time.sleep(0.5)
                    st.rerun()

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

        st.markdown("---")
        st.subheader("📱 微信公众号推文生成")
        use_wechat = st.checkbox("生成微信公众号推文 (跳过常规图表渲染加速)")
        wechat_prompt = ""
        if use_wechat:
            wechat_prompt = st.text_area("推文个性化要求 (可选)", placeholder="例如：语气更加诙谐幽默，重点强调端侧存储，多用短句...", height=68)

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
                    
                    if raw.startswith("获取失败") or raw.startswith("获取异常") or raw.startswith("跳过分析") or (not briefs and not f_list):
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
                            
                    if use_wechat:
                        main_status.write("📱 **正在创作微信公众号推文** (包含智能配图)...")
                        wechat_system_prompt = """你是一个顶级的科技/金融类微信公众号爆款作者。
请根据以下 AI 深度分析的结论，将其重写为一篇适合微信公众号发布的推文。
【核心要求】：
1. 结构化排版：必须包含吸睛的标题（无需加#号）、引言、逻辑清晰的分层正文、结尾总结。
2. 语言风格：通俗易懂，大白话，有极强的情绪价值和代入感（就像和朋友面对面聊天）。如果用户提供了个性化要求，必须优先满足。
3. 智能配图（核心必做）：为了达到图文并茂的效果，你必须在文章的关键位置（如标题下方或每个重要章节的开头）插入 2 到 3 张图片。
   插入图片的 Markdown 格式严格为：`![图片说明]([IMAGE_SEARCH:核心中英文提示词])`。
   ⚠️ 警告：中括号内必须填入与上下文最相关的关键词（可以包含中文或英文），例如 `![AI芯片]([IMAGE_SEARCH:AI芯片 算力中心])`。
4. 结尾固定免责声明：在文章的最后，必须一字不差地加上以下免责声明：
> 本文内容及数据均基于公开市场资料与行业研报，仅作产业趋势分析与逻辑梳理之用，旨在探讨技术发展方向与产业格局变迁，不构成任何具体的投资建议或操作指引。文中提及的企业及产品仅作为产业案例分析，不构成推荐。投资有风险，入市需谨慎。请您基于自身独立判断做出决策。"""
                        
                        wechat_user_content = f"【基础分析总结】\n{final_res}\n"
                        if wechat_prompt.strip():
                            wechat_user_content += f"\n【用户个性化要求】\n{wechat_prompt}"
                            
                        try:
                            from openai import OpenAI
                            client = OpenAI(api_key=current_chan_config.get("api_key"), base_url=current_chan_config.get("base_url") if current_chan_config.get("base_url") else None)
                            wc_response = client.chat.completions.create(model=current_chan_config.get("selected_model"), messages=[{"role": "system", "content": wechat_system_prompt}, {"role": "user", "content": wechat_user_content}])
                            if wc_response.choices:
                                raw_wechat = wc_response.choices[0].message.content
                                import re
                                def replace_img(match):
                                    kw = match.group(1)
                                    img_url = get_bing_image(kw)
                                    return f"({img_url})"
                                    
                                wechat_res = re.sub(r'\(\[IMAGE_SEARCH:(.*?)\]\)', replace_img, raw_wechat)
                                st.session_state['latest_wechat'] = wechat_res
                            else:
                                main_status.write("⚠️ 微信公众号推文生成返回为空")
                        except Exception as e:
                            main_status.write(f"⚠️ 微信公众号推文生成失败: {str(e)}")

                    if not use_wechat:
                        main_status.write("🎨 正在渲染专业分析报表...")
                        img_p = render_to_image(final_res, a_mode)
                        st.session_state['latest_img'] = img_p
                        
                    main_status.update(label="🎉 任务完成！", state="complete", expanded=False)

            if not use_wechat:
                st.success("分析报表已生成！请在右侧预览。")
            else:
                st.success("微信公众号推文已生成！请在右侧预览。")
            time.sleep(1)
            st.rerun()

    with col2:
        tab1, tab2 = st.tabs(["📊 分析报告预览", "📱 公众号推文预览"])
        
        with tab1:
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
                            
        with tab2:
            if st.session_state.get('latest_wechat'):
                st.download_button(
                    label="📄 导出推文为 Docx 文档",
                    data=markdown_to_wechat_docx_bytes(st.session_state['latest_wechat']),
                    file_name=f"微信公众号推文_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    type="primary"
                )
                
                st.markdown(
                    """
                    <style>
                    .wechat-container {
                        max-width: 480px;
                        margin: 16px auto;
                        background-color: white;
                        border-radius: 12px;
                        padding: 24px 16px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                        color: #333;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    }
                    .wechat-container img {
                        width: 100%;
                        border-radius: 8px;
                        margin: 16px 0;
                    }
                    .wechat-container h1, .wechat-container h2, .wechat-container h3 {
                        color: #1a1a1a;
                    }
                    .wechat-container blockquote {
                        border-left: 4px solid #07c160;
                        background: #f7f7f7;
                        margin: 16px 0;
                        padding: 12px;
                        color: #666;
                        font-size: 0.9em;
                    }
                    </style>
                    """, unsafe_allow_html=True
                )
                
                st.markdown('<div class="wechat-container">', unsafe_allow_html=True)
                st.markdown(st.session_state['latest_wechat'], unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("暂无生成的公众号推文。请在左侧勾选「同步生成微信公众号推文」并开始深度分析。")

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
                    user_content += f"请根据以上提供的历史脚本风格进行学习。你的核心任务是**直接生成一篇全新的完整视频脚本（最终提词器念稿版本）**，绝对不要只输出分析总结，也不要向我提问索要素材。\n"
                    if prompt_input.strip():
                        user_content += f"\n[新素材与要求]：\n{prompt_input}\n\n请结合上述新素材生成脚本内容。"
                    else:
                        user_content += "\n由于用户没有提供新素材，请自行发挥你的专业金融编导水平，拟定一个符合当前市场热点的主题，直接撰写出这篇完整的视频脚本。"
                else:
                    user_content += f"请深度分析前面提供的历史脚本序列的故事线、知识递进逻辑和表达手法，自动推理出下一期的主题，并**直接【顺延生成】最新一期的完整视频脚本内容（最终提词器念稿版本）**。要求保持一贯的口语化、设问式风格。绝对不要向我提问索要素材，也绝对不要仅仅输出风格特征分析表！\n"
                    if prompt_input.strip():
                        user_content += f"\n在续写时，请必须结合以下新素材或要求：\n[新素材与要求]：\n{prompt_input}"
                    else:
                        user_content += "\n请注意：由于我没有提供新素材，请直接根据历史上下文的逻辑推演，自动拟定下一期主题并生成完整的视频文案！"
                
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

elif page_selection == "指标文档制作":
    st.title("📈 指标文档制作")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("⚙️ 1. 指标库管理")
        indicators = load_indicators()
        ind_options = ["✨ [新建空白指标]"] + list(indicators.keys())
        
        # Maintain selection state
        if "ind_selected" not in st.session_state: st.session_state["ind_selected"] = ind_options[0]
        sel_ind = st.selectbox("选择或新建指标", ind_options, index=ind_options.index(st.session_state["ind_selected"]) if st.session_state["ind_selected"] in ind_options else 0)
        
        if sel_ind != st.session_state["ind_selected"]:
            st.session_state["ind_selected"] = sel_ind
            st.rerun()
        
        if sel_ind == "✨ [新建空白指标]":
            def_name = ""
            def_code = ""
        else:
            def_name = sel_ind
            def_code = indicators[sel_ind]["code"]
            
        new_ind_name = st.text_input("指标名称", value=def_name, placeholder="例如：震荡顶底模型")
        new_ind_code = st.text_area("指标源码", value=def_code, height=200, placeholder="在此粘贴 Pine Script 或 Python 源码...")
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("💾 保存/更新", use_container_width=True):
                if new_ind_name.strip() and new_ind_code.strip():
                    save_indicator(new_ind_name.strip(), new_ind_code.strip())
                    st.session_state["ind_selected"] = new_ind_name.strip()
                    st.success(f"指标 '{new_ind_name}' 已保存！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("名称和源码不能为空！")
        with c_btn2:
            if st.button("🗑️ 删除", use_container_width=True):
                if sel_ind != "✨ [新建空白指标]":
                    delete_indicator(sel_ind)
                    st.session_state["ind_selected"] = "✨ [新建空白指标]"
                    st.success(f"指标 '{sel_ind}' 已删除！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("新建状态不可删除")
                    
        st.markdown("---")
        st.subheader("⚡ 2. 生成分析文档")
        
        if not indicators:
            st.info("暂无已保存的指标，请先保存指标后再生成。")
        else:
            gen_ind = st.selectbox("选择目标指标", list(indicators.keys()), index=list(indicators.keys()).index(st.session_state["ind_selected"]) if st.session_state["ind_selected"] in indicators else 0)
            
            if st.button("🚀 生成标准合规版", type="primary", use_container_width=True):
                if not current_chan_config.get("api_key"): st.error("请先在左侧全局配置中填写 API Key！")
                else:
                    with st.status("正在生成标准合规分析文档...", expanded=True) as status:
                        st.write(f"🧠 AI 正在分析 {gen_ind} 的源码...")
                        user_content = f"【指标名称】：{gen_ind}\n【指标源码】：\n{indicators[gen_ind]['code']}"
                        try:
                            client = OpenAI(api_key=current_chan_config.get("api_key"), base_url=current_chan_config.get("base_url") if current_chan_config.get("base_url") else None)
                            response = client.chat.completions.create(
                                model=current_chan_config.get("selected_model"),
                                messages=[
                                    {"role": "system", "content": PROMPT_INDICATOR_STANDARD},
                                    {"role": "user", "content": user_content}
                                ]
                            )
                            if not response.choices: raise Exception("接口返回空数据")
                            doc_content = response.choices[0].message.content
                            
                            ts = datetime.now().strftime("%Y%m%d%H%M%S")
                            md_filename = f"《{gen_ind}》---合规化_{ts}.md"
                            docx_filename = f"《{gen_ind}》---合规化_{ts}.docx"
                            md_path = os.path.join(INDICATOR_DOCS_DIR, md_filename)
                            docx_path = os.path.join(INDICATOR_DOCS_DIR, docx_filename)
                            
                            with open(md_path, "w", encoding="utf-8") as f: f.write(doc_content)
                            markdown_to_docx_file(doc_content, docx_path, indicator_name=gen_ind)
                            
                            st.session_state["ind_preview_title"] = f"{gen_ind} (标准合规版)"
                            st.session_state["ind_preview_content"] = doc_content
                            st.session_state["ind_preview_docx"] = docx_path
                            
                            status.update(label="标准文档生成完成！", state="complete", expanded=False)
                            st.rerun()
                        except Exception as e:
                            status.update(label="生成失败", state="error")
                            st.error(f"报错信息: {str(e)}")
                            
            if st.button("✨ 基于标准版一键转化【社群互动教学】版", use_container_width=True):
                if not current_chan_config.get("api_key"): st.error("请先填写 API Key！")
                elif "ind_preview_content" not in st.session_state or "合规化" not in st.session_state.get("ind_preview_title", ""):
                    st.warning("请先生成或从右侧历史预览一份【标准合规版】文档，再进行转化！")
                else:
                    with st.status("正在进行社群风格转换...", expanded=True) as status2:
                        try:
                            client = OpenAI(api_key=current_chan_config.get("api_key"), base_url=current_chan_config.get("base_url") if current_chan_config.get("base_url") else None)
                            response2 = client.chat.completions.create(
                                model=current_chan_config.get("selected_model"),
                                messages=[
                                    {"role": "system", "content": PROMPT_INDICATOR_COMMUNITY},
                                    {"role": "user", "content": f"请将以下标准技术文档转化为社群教学版本：\n\n{st.session_state['ind_preview_content']}"}
                                ]
                            )
                            if not response2.choices: raise Exception("接口返回空数据")
                            comm_doc = response2.choices[0].message.content
                            
                            ts = datetime.now().strftime("%Y%m%d%H%M%S")
                            md_filename = f"《{gen_ind}》--社群指标互动手册_{ts}.md"
                            docx_filename = f"《{gen_ind}》--社群指标互动手册_{ts}.docx"
                            md_path = os.path.join(INDICATOR_DOCS_DIR, md_filename)
                            docx_path = os.path.join(INDICATOR_DOCS_DIR, docx_filename)
                            
                            with open(md_path, "w", encoding="utf-8") as f: f.write(comm_doc)
                            markdown_to_docx_file(comm_doc, docx_path, indicator_name=gen_ind)
                            
                            st.session_state["ind_preview_title"] = f"{gen_ind} (社群互动教学版)"
                            st.session_state["ind_preview_content"] = comm_doc
                            st.session_state["ind_preview_docx"] = docx_path
                            
                            status2.update(label="社群文档转换完成！", state="complete", expanded=False)
                            st.rerun()
                        except Exception as e:
                            status2.update(label="转换失败", state="error")
                            st.error(f"报错信息: {str(e)}")

    with col2:
        st.subheader("👁️ 3. 预览与归档")
        
        preview_title = st.session_state.get("ind_preview_title", "预览区")
        preview_content = st.session_state.get("ind_preview_content", "")
        
        with st.container(border=True):
            st.markdown(f"#### {preview_title}")
            if preview_content:
                st.markdown(preview_content)
                docx_path = st.session_state.get("ind_preview_docx")
                if docx_path and os.path.exists(docx_path):
                    with open(docx_path, "rb") as f: docx_data = f.read()
                    st.download_button(
                        label="⬇️ 下载该 Docx 文档",
                        data=docx_data,
                        file_name=os.path.basename(docx_path),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        type="primary"
                    )
            else:
                st.info("右侧暂无预览，请在左侧操作生成或从历史归档中选择。")
                
        st.markdown("---")
        st.write("### 📅 历史报告归档")
        hist_docs = sorted(glob.glob(os.path.join(INDICATOR_DOCS_DIR, "*.md")), reverse=True)
        if not hist_docs:
            st.info("暂无生成的文档归档。")
        else:
            # 按日期分组
            grouped_files = {}
            for h_md in hist_docs:
                basename = os.path.basename(h_md)
                match = re.search(r'_(\d{8})\d{6}\.md$', basename)
                if match:
                    date_str = datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
                else:
                    mtime = os.path.getmtime(h_md)
                    date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                
                if date_str not in grouped_files:
                    grouped_files[date_str] = []
                grouped_files[date_str].append(h_md)
            
            # 日期下拉菜单
            date_list = sorted(grouped_files.keys(), reverse=True)
            selected_date = st.selectbox("选择日期", date_list, index=0, key="hist_date_select")
            
            # 仅展示所选日期的文件
            if selected_date in grouped_files:
                for h_md in grouped_files[selected_date]:
                    basename = os.path.basename(h_md)
                    with st.expander(f"📄 {basename}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("👁️ 在上方预览", key=f"prev_{h_md}", use_container_width=True):
                                with open(h_md, "r", encoding="utf-8") as f: content = f.read()
                                docx_p = h_md.replace(".md", ".docx")
                                st.session_state["ind_preview_title"] = basename.replace(".md", "")
                                st.session_state["ind_preview_content"] = content
                                st.session_state["ind_preview_docx"] = docx_p if os.path.exists(docx_p) else ""
                                st.rerun()
                        with c2:
                            docx_p = h_md.replace(".md", ".docx")
                            if os.path.exists(docx_p):
                                with open(docx_p, "rb") as f: db = f.read()
                                st.download_button(
                                    label="⬇️ 下载 Docx",
                                    data=db,
                                    file_name=os.path.basename(docx_p),
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    key=f"dl_{docx_p}",
                                    use_container_width=True
                                )

