import os
import re
import sys
import subprocess
import base64
import time
import uuid
import httpx
import markdown
from datetime import datetime
from playwright.sync_api import sync_playwright

WECHAT_IMAGES_DIR = os.path.join("outputs", "wechat", "images")
IMAGE_OUTPUT_DIR = os.path.join("outputs", "images")

def generate_jimeng_image(prompt_text, retries=1):
    import re
    import time
    for attempt in range(retries + 1):
        try:
            # Call Dreamina CLI to generate image. --poll=120 will wait up to 120 seconds.
            # Ensure we output JSON or parse text carefully.
            res = subprocess.run([DREAMINA_CMD, "text2image", f"--prompt={prompt_text}", "--poll=120"], capture_output=True, text=True, encoding='utf-8')
            # Expecting output containing URL or similar, since dreamina text2image might output a result message
            # We look for https://... link to the generated image
            # Let's extract URLs from the output
            urls = re.findall(r'https?://[^\s\"\'\)]+', res.stdout)
            img_url = None
            for u in urls:
                if "tos-" in u or "image" in u or ".png" in u or ".jpg" in u or ".jpeg" in u or ".webp" in u:
                    img_url = u
                    break
            if not img_url and urls:
                img_url = urls[-1] # fallback to the last URL found
                
            if img_url:
                # Download the image
                import httpx
                import uuid
                img_resp = httpx.get(img_url, timeout=30)
                if img_resp.status_code == 200:
                    filename = f"jimeng_{uuid.uuid4().hex[:8]}.jpg"
                    filepath = os.path.join(WECHAT_IMAGES_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(img_resp.content)
                    return filepath
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2)
    return None

def generate_gemini_image(prompt_text, api_key, model_name="imagen-4.0-generate-001", aspect_ratio="1:1", retries=2):
    import base64
    import time
    import httpx
    import uuid
    
    if not api_key:
        return None
        
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=60.0) as client:
                if "gemini" in model_name:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{"parts": [{"text": prompt_text}]}],
                        "generationConfig": {
                            "responseModalities": ["IMAGE"]
                        }
                    }
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        resp_json = resp.json()
                        parts = resp_json.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        img_data = None
                        for p in parts:
                            if "inlineData" in p:
                                b64 = p["inlineData"]["data"]
                                img_data = base64.b64decode(b64)
                                break
                        if img_data:
                            filename = f"gemini_{uuid.uuid4().hex[:8]}.jpg"
                            filepath = os.path.join(WECHAT_IMAGES_DIR, filename)
                            with open(filepath, "wb") as f:
                                f.write(img_data)
                            return filepath
                    else:
                        print(f"Gemini Image Gen failed, status code: {resp.status_code}, response: {resp.text[:200]}")
                else:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "instances": [{"prompt": prompt_text}],
                        "parameters": {
                            "sampleCount": 1,
                            "aspectRatio": aspect_ratio
                        }
                    }
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        resp_json = resp.json()
                        predictions = resp_json.get("predictions", [])
                        if predictions:
                            img_b64 = predictions[0].get("bytesBase64Encoded")
                            if img_b64:
                                img_data = base64.b64decode(img_b64)
                                filename = f"gemini_{uuid.uuid4().hex[:8]}.jpg"
                                filepath = os.path.join(WECHAT_IMAGES_DIR, filename)
                                with open(filepath, "wb") as f:
                                    f.write(img_data)
                                return filepath
                    else:
                        print(f"Gemini Image Gen failed, status code: {resp.status_code}, response: {resp.text[:200]}")
        except (OSError, httpx.HTTPError, httpx.RequestError) as e:
            print(f"Gemini Image Gen network/socket error (attempt {attempt+1}/{retries+1}): {str(e)}")
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:
            print(f"Gemini Image Gen unexpected error: {str(e)}")
            
        if attempt < retries:
            time.sleep(2.0)
    return None

def adjust_markdown_images_placement(md_text):
    import re
    lines = md_text.split('\n')
    sections = []
    current_section = []
    
    for line in lines:
        if line.strip().startswith('#'):
            if current_section:
                sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)
        
    new_sections = []
    for sec in sections:
        if not sec:
            continue
        if sec[0].strip().startswith('#'):
            heading = sec[0]
            content_lines = sec[1:]
            
            img_lines = []
            other_lines = []
            img_pattern = re.compile(r'!\[.*?\]\((?:\[IMAGE_GENERATE:.*?\]|.*?)\)')
            
            for line in content_lines:
                if img_pattern.search(line):
                    img_lines.append(line)
                else:
                    other_lines.append(line)
            
            if img_lines:
                new_sec = [heading]
                for img in img_lines:
                    new_sec.append(img)
                while other_lines and not other_lines[0].strip():
                    other_lines.pop(0)
                new_sec.extend(other_lines)
                new_sections.append(new_sec)
            else:
                new_sections.append(sec)
        else:
                        new_sections.append(sec)
            
    flat_lines = []
    for sec in new_sections:
        flat_lines.extend(sec)
    return '\n'.join(flat_lines)

def ensure_image_prompts_exist(md_text: str) -> str:
    """
    检查 Markdown 文章中的标题。若标题下方缺失 [IMAGE_GENERATE:] 配图标记，
    自动在标题正下方补齐对应英文 Prompt 的配图标记，保底 100% 触发 Gemini / 即梦生图。
    """
    if not md_text:
        return md_text

    lines = md_text.split("\n")
    new_lines = []
    
    img_pattern = re.compile(r'\(?\[?IMAGE_GENERATE:\s*(.*?)\)?\]?')
    
    for i, line in enumerate(lines):
        new_lines.append(line)
        stripped = line.strip()
        # 匹配标题 (# H1, ## H2, ### H3)
        if stripped.startswith("#"):
            # 检查接下来 4 行内是否已经有 IMAGE_GENERATE 标记
            has_image = False
            for j in range(i + 1, min(i + 5, len(lines))):
                if img_pattern.search(lines[j]):
                    has_image = True
                    break
            
            if not has_image:
                title_clean = re.sub(r'^#+\s*', '', stripped)
                title_clean = re.sub(r'[\*\`_~]', '', title_clean).strip()
                title_clean = re.sub(r'^[一二三四五六七八九十0-9\.\s]+', '', title_clean)
                if not title_clean:
                    title_clean = "financial technology industry chart"
                
                prompt_tag = f"\n![{title_clean}]([IMAGE_GENERATE:A realistic photography visualization of {title_clean}, technology and financial aesthetic, cinematic lighting, 8k resolution, photorealistic])\n"
                new_lines.append(prompt_tag)
                
    return "\n".join(new_lines)

def generate_wechat_long_image(html_content):
    import os
    from datetime import datetime
    from playwright.sync_api import sync_playwright
    
    output_filename = f"wechat_long_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    output_path = os.path.join(WECHAT_IMAGES_DIR, output_filename)
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 450, "height": 800})
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=output_path, full_page=True)
        browser.close()
        
    return output_path

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

