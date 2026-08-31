import os
import re
import json
import subprocess
import time
import httpx
import llm
from config_store import get_exec_env as _get_exec_env

NPX_CMD = "npx.cmd" if os.name == "nt" else "npx"

def fetch_zsxq(group_id, limit=3, scope="all", progress_callback=None):
    if not group_id:
        return "请提供知识星球的 Group ID。", [], []
    
    processed_files = []
    processed_topics_brief = []
    
    # 1. Auth check
    if progress_callback: progress_callback({"type": "info", "msg": "正在检查授权状态..."})
    status_res = subprocess.run([NPX_CMD, "zsxq-cli", "auth", "status", "--json"], capture_output=True, text=True, encoding='utf-8', env=_get_exec_env())
    is_logged = False
    try:
        m = re.search(r'\{.*\}', status_res.stdout, re.DOTALL)
        if m:
            auth_data = json.loads(m.group(0))
            if auth_data.get("ok") and auth_data.get("data", {}).get("loggedIn"):
                is_logged = True
    except Exception: pass
    
    if not is_logged:
        return "获取失败: 知识星球未授权。请在左侧边栏获取授权链接。", [], []

    # 2. Fetch topics
    if progress_callback: progress_callback({"type": "info", "msg": "正在向知识星球请求最新动态..."})
    # 始终拉取最大 30 条动态，供顺位过滤，防止因前面的动态是 MP3 或空动态而导致无法顺位往下获取
    fetch_limit = 30
    max_retries = 3
    import time
    for attempt in range(max_retries):
        result = subprocess.run([
            NPX_CMD, "zsxq-cli", "group", "+topics", "--group-id", str(group_id), "--limit", str(fetch_limit), "--json"
        ], capture_output=True, text=True, encoding='utf-8', timeout=45, env=_get_exec_env())
        
        if result.returncode == 0:
            break
            
        err_msg = result.stderr.strip() if result.stderr else (result.stdout.strip() if result.stdout else "CLI 内部错误")
        if any(keyword in err_msg.upper() for keyword in ["EOF", "TRANSPORT", "TIMEOUT", "CONNECTION", "CLOSED"]):
            if attempt < max_retries - 1:
                sleep_sec = 3 * (attempt + 1)
                if progress_callback: 
                    progress_callback({"type": "info", "msg": f"⚠️ 网络请求异常 ({err_msg})，将在 {sleep_sec} 秒后进行第 {attempt+2} 次重试..."})
                time.sleep(sleep_sec)
                continue
                
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
                        dl_res = None
                        for dl_attempt in range(3):
                            dl_res = subprocess.run([NPX_CMD, "zsxq-cli", "api", "call", "call_zsxq_api", "--params", json.dumps({"method": "GET", "path": f"/v2/files/{fid}/download_url"})], capture_output=True, text=True, encoding='utf-8', timeout=15, env=_get_exec_env())
                            if dl_res.returncode == 0:
                                break
                            time.sleep(2 * (dl_attempt + 1))
                        dl_m = re.search(r'\{.*\}', dl_res.stdout, re.DOTALL)
                        if dl_m:
                            res_json = json.loads(dl_m.group(0))
                            dl_url = (
                                res_json.get('download_url') or 
                                res_json.get('body', {}).get('resp_data', {}).get('download_url') or 
                                res_json.get('body', {}).get('download_url') or 
                                res_json.get('data', {}).get('download_url')
                            )
                            if dl_url:
                                f_raw = httpx.get(dl_url, timeout=30).content
                                extracted = ""
                                if fname.lower().endswith('.pdf'):
                                    extracted = llm.extract_text_from_pdf(f_raw)
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
