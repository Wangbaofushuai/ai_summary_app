import os
import json
import time
import re
import html
import httpx
from pathlib import Path

# 全局 Token 内存缓存 appid -> {"token": ..., "expires_at": ...}
_TOKEN_CACHE = {}

def get_server_ip() -> str:
    """获取执行机的公网 IP 供配置白名单使用"""
    ips = []
    
    # 1. 尝试获取国内直连/国内路由出口 IP (在有代理分流的环境下检测国内网络看到的 IP)
    cn_urls = [
        "http://myip.ipip.net",
        "https://pv.sohu.com/cityjson?ie=utf-8"
    ]
    for url in cn_urls:
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    text = res.text
                    m = re.search(r'((?:[0-9]{1,3}\.){3}[0-9]{1,3})', text)
                    if m:
                        ip = m.group(1)
                        if ip not in ips and ip != "127.0.0.1":
                            ips.append(ip)
                            break
        except Exception:
            continue
            
    # 2. 尝试获取国际/代理出口 IP
    global_urls = [
        "https://api.ipify.org",
        "https://httpbin.org/ip",
        "https://ipinfo.io/ip",
        "https://ifconfig.me"
    ]
    for url in global_urls:
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    text = res.text.strip()
                    if "origin" in text:
                        ip = res.json().get("origin", "").split(",")[0].strip()
                    else:
                        ip = text
                    m = re.search(r'((?:[0-9]{1,3}\.){3}[0-9]{1,3})', ip)
                    if m:
                        found_ip = m.group(1)
                        if found_ip not in ips:
                            ips.append(found_ip)
                            break
        except Exception:
            continue
            
    if ips:
        # 如果有多个不同 IP，说明存在代理/分流出口，以斜杠分隔展现
        return " / ".join(ips)
    return "无法获取公网 IP，请检查服务器网络。"

def load_accounts(config_path: str = "config.json") -> list:
    """从 config.json 加载公众号账号配置"""
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("wechat_accounts", [])
    except Exception:
        return []

def save_accounts(accounts: list, config_path: str = "config.json") -> bool:
    """保存公众号账号配置回 config.json"""
    if not os.path.exists(config_path):
        data = {}
    else:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    
    data["wechat_accounts"] = accounts
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

def get_access_token(appid: str, secret: str) -> str:
    """获取公众号 Access Token 并带缓存机制"""
    appid = appid.strip()
    secret = secret.strip()
    now = time.time()
    
    # 检查缓存是否有效
    if appid in _TOKEN_CACHE:
        cache = _TOKEN_CACHE[appid]
        if cache["expires_at"] > now:
            return cache["token"]
            
    # 请求接口
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret
    }
    
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url, params=params)
            res.raise_for_status()
            data = res.json()
            
        if "access_token" in data:
            token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            # 缓存提前 200 秒过期以确保安全
            _TOKEN_CACHE[appid] = {
                "token": token,
                "expires_at": now + expires_in - 200
            }
            return token
        else:
            err_msg = data.get("errmsg", "未知错误")
            err_code = data.get("errcode", -1)
            raise Exception(f"获取微信凭证失败: {err_msg} (错误码: {err_code})")
    except httpx.HTTPError as e:
        raise Exception(f"微信接口请求失败: {str(e)}")

def upload_body_image(image_path: str, access_token: str) -> str:
    """上传文章正文内图片，返回微信 CDN URL (不占用永久素材额度)"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"本地图片不存在: {image_path}")
        
    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    
    # 提取文件名
    filename = os.path.basename(image_path)
    
    with open(image_path, "rb") as f:
        files = {"media": (filename, f, "image/jpeg")}
        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, files=files)
            res.raise_for_status()
            data = res.json()
            
    if "url" in data:
        return data["url"]
    else:
        err_msg = data.get("errmsg", "未知错误")
        err_code = data.get("errcode", -1)
        raise Exception(f"正文图片上传微信失败: {err_msg} (码: {err_code})")

def upload_cover_image(image_path: str, access_token: str) -> str:
    """上传封面图片到永久素材库，返回 media_id"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"本地图片不存在: {image_path}")
        
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    filename = os.path.basename(image_path)
    
    with open(image_path, "rb") as f:
        files = {"media": (filename, f, "image/jpeg")}
        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, files=files)
            res.raise_for_status()
            data = res.json()
            
    if "media_id" in data:
        return data["media_id"]
    else:
        err_msg = data.get("errmsg", "未知错误")
        err_code = data.get("errcode", -1)
        raise Exception(f"封面图片上传微信失败: {err_msg} (码: {err_code})")

def replace_local_images_with_wechat_urls(html_content: str, access_token: str, local_images_dir: str = "outputs/wechat/images") -> str:
    """解析 HTML，上传其中引用的本地图片并替换为微信 CDN URL"""
    # 匹配 src="outputs/wechat/images/xxx.jpg" 或 src="data:image/..." 
    # 注意：如果之前有 base64 替换，我们应该还原或基于最初生成的本地图片路径进行上传
    # 最好是直接在 HTML 里匹配所有引用的本地路径
    
    # 查找本地路径引用的正则表达式
    # 示例: src="outputs/wechat/images/gemini_xxxx.jpg"
    img_src_pattern = re.compile(r'src=["\'](outputs/wechat/images/[^"\']+)["\']', re.IGNORECASE)
    
    # 针对可能已被 base64 替换的 src, 我们可以先做一次逆映射 (如果有必要),
    # 但由于 app.py 中先生成 base64 供 iframe 实时预览，因此我们要上传微信时，最好是拿一份干净的、没有转成 base64 的原始 HTML
    # 或者我们的发布函数接收 markdown 内容后重新运行转换或传入含有原始本地路径的 HTML 文本。
    # 这里我们假设传入的 HTML 内容中还保留了本地路径 (我们在 app.py 中保存一份原始 HTML 文本即可)。
    
    matches = img_src_pattern.findall(html_content)
    unique_paths = list(set(matches))
    
    uploaded_cache = {}
    
    for path in unique_paths:
        normalized_path = os.path.normpath(path)
        if os.path.exists(normalized_path):
            try:
                wechat_url = upload_body_image(normalized_path, access_token)
                uploaded_cache[path] = wechat_url
            except Exception as e:
                # 记录失败，如果上传失败，保留原路径或跳过
                print(f"上传正文配图失败 {normalized_path}: {str(e)}")
                
    # 进行替换
    new_html = html_content
    for local_path, wechat_url in uploaded_cache.items():
        new_html = new_html.replace(local_path, wechat_url)
        # 兼容反斜杠
        alt_path = local_path.replace("/", "\\")
        new_html = new_html.replace(alt_path, wechat_url)
        
    return new_html

def create_draft(access_token: str, title: str, author: str, digest: str, content_html: str, cover_media_id: str) -> str:
    """创建草稿箱文章，返回 media_id"""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"
    
    # 微信接口解码 HTML 转义字符，如 &ldquo; -> “ 等
    title = html.unescape(title or "")
    author = html.unescape(author or "")
    digest = html.unescape(digest or "")
    content_html = html.unescape(content_html or "")
    
    # 物理删除所有 Emoji 表情符号，防过滤遗漏
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)
    title = emoji_pattern.sub('', title)
    author = emoji_pattern.sub('', author)
    digest = emoji_pattern.sub('', digest)
    content_html = emoji_pattern.sub('', content_html)
    
    article = {
        "title": title[:32], # 微信限制标题 32 字
        "author": author[:16], # 作者限制 16 字
        "digest": digest[:128] if digest else "点击阅读全文", # 摘要限制 128 字
        "content": content_html,
        "thumb_media_id": cover_media_id,
        "show_cover_pic": 1,
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    }
    
    body = {
        "articles": [article]
    }
    
    # 微信接口要求非 ASCII 字符必须以 UTF-8 编码传输且保留原始字符 (ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    
    with httpx.Client(timeout=30.0) as client:
        res = client.post(url, headers=headers, content=payload)
        res.raise_for_status()
        data = res.json()
        
    if "media_id" in data:
        return data["media_id"]
    else:
        err_msg = data.get("errmsg", "未知错误")
        err_code = data.get("errcode", -1)
        raise Exception(f"创建微信草稿失败: {err_msg} (码: {err_code})")

def get_draft_url(access_token: str, media_id: str) -> str:
    """获取草稿文章的临时预览链接"""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/get?access_token={access_token}"
    body = {
        "media_id": media_id
    }
    
    with httpx.Client(timeout=20.0) as client:
        res = client.post(url, json=body)
        res.raise_for_status()
        data = res.json()
        
    if "news_item" in data and len(data["news_item"]) > 0:
        return data["news_item"][0].get("url", "")
    else:
        err_msg = data.get("errmsg", "未知错误")
        err_code = data.get("errcode", -1)
        raise Exception(f"获取微信草稿链接失败: {err_msg} (码: {err_code})")

def send_preview(access_token: str, media_id: str, wx_name: str) -> bool:
    """发送群发预览给指定的微信号"""
    url = f"https://api.weixin.qq.com/cgi-bin/message/mass/preview?access_token={access_token}"
    
    body = {
        "towxname": wx_name.strip(),
        "mpnews": {
            "media_id": media_id
        },
        "msgtype": "mpnews"
    }
    
    # 微信接收预览要求 UTF-8
    headers = {"Content-Type": "application/json"}
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    
    with httpx.Client(timeout=20.0) as client:
        res = client.post(url, headers=headers, content=payload)
        res.raise_for_status()
        data = res.json()
        
    err_code = data.get("errcode", 0)
    if err_code == 0:
        return True
    else:
        err_msg = data.get("errmsg", "发送预览失败")
        raise Exception(f"微信群发预览失败: {err_msg} (码: {err_code})")

def publish_draft(access_token: str, media_id: str) -> str:
    """一键正式发布草稿箱的文章 (无群发限制发布)"""
    url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}"
    body = {
        "media_id": media_id
    }
    
    with httpx.Client(timeout=20.0) as client:
        res = client.post(url, json=body)
        res.raise_for_status()
        data = res.json()
        
    if "publish_id" in data or data.get("errcode", 0) == 0:
        return data.get("publish_id", "published")
    else:
        err_msg = data.get("errmsg", "发布失败")
        err_code = data.get("errcode", -1)
        raise Exception(f"正式发布草稿失败: {err_msg} (码: {err_code})")

def save_draft_info(md_filepath: str, media_id: str, url: str, status: str = "draft", publish_time: str = None, scheduled_time: str = None, appid: str = None, secret: str = None):
    """保存微信草稿信息（MediaID 和预览 URL）到对应的 .draft.json 关联文件中"""
    if not md_filepath:
        return
    p = Path(md_filepath)
    draft_file = p.with_suffix(".draft.json")
    
    # 采用合并模式，防止更新部分字段时将原本的 appid 或 secret 冲掉
    data = load_draft_info(md_filepath)
    
    if media_id:
        data["media_id"] = media_id
    if url:
        data["url"] = url
        
    data["status"] = status
    
    if publish_time is not None:
        data["publish_time"] = publish_time
    else:
        # 如果 status 为 published 且没有传发布时间，则自动记录当前时间
        if status == "published" and "publish_time" not in data:
            import datetime
            data["publish_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
    if scheduled_time is not None:
        data["scheduled_time"] = scheduled_time
    if appid is not None:
        data["appid"] = appid
    if secret is not None:
        data["secret"] = secret
        
    with open(draft_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_draft_info(md_filepath: str) -> dict:
    """从 .draft.json 关联文件中加载微信草稿信息"""
    if not md_filepath:
        return {}
    p = Path(md_filepath)
    draft_file = p.with_suffix(".draft.json")
    if os.path.exists(draft_file):
        try:
            with open(draft_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def auto_publish_to_wechat(md_filepath: str, html_filepath: str, account_config: dict, publish_mode: str) -> dict:
    """自动化一键处理微信草稿创建和正式发布流程（供定时任务使用）
    publish_mode:
        - "自动保存至微信草稿箱"
        - "自动保存草稿并正式发布"
    """
    if not os.path.exists(md_filepath) or not os.path.exists(html_filepath):
        raise FileNotFoundError("找不到指定的 Markdown 或 HTML 文件")

    # 1. 读取 markdown 提取元数据
    with open(md_filepath, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 提取标题
    title = "技术分析报告"
    for line in md_text.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            parsed_title = re.sub(r'^#+\s*', '', line).strip()
            if parsed_title:
                title = parsed_title
                break
    
    # 微信限制标题 32 字，此处截断
    if len(title) > 32:
        title = title[:32]

    # 提取摘要（清理格式后的前 80 字符）
    clean_text = re.sub(r'!\[[^\]]*\]\s*\([^)]*\)', '', md_text)
    clean_text = re.sub(r'\[[^\]]*\]\s*\([^)]*\)', '', clean_text)
    clean_text = re.sub(r'<[^>]*>', '', clean_text)
    clean_text = re.sub(r'outputs[/\\]wechat[/\\]images[/\\][^\s]+', '', clean_text)
    clean_text = re.sub(r'\(\s*outputs[/\\]wechat[/\\]images[/\\][^\s]*\)', '', clean_text)
    clean_text = re.sub(r'[#\*_`\-\>\+\n\r\t]', ' ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    digest = clean_text[:80] + "..." if len(clean_text) > 80 else clean_text
    if not digest:
        digest = "点击阅读全文"

    # 提取封面图
    img_pattern = re.compile(r'!\[.*?\]\s*\(\s*([^)\s]+\.(?:jpg|png|jpeg|webp))\s*\)', re.IGNORECASE)
    found_imgs = img_pattern.findall(md_text)
    
    cover_path = None
    for img in found_imgs:
        img_path = img.replace("\\", "/").strip()
        paths_to_check = [img_path]
        if img_path.startswith("/"):
            paths_to_check.append(img_path[1:])
        else:
            paths_to_check.append("/" + img_path)
            
        for p in paths_to_check:
            if os.path.exists(p) and not os.path.isdir(p):
                cover_path = p
                break
        if cover_path:
            break

    # 如果没有找到任何图片，使用默认的 logo.png
    if not cover_path:
        if os.path.exists("logo.png"):
            cover_path = "logo.png"
        else:
            raise FileNotFoundError("未在推文中发现任何配图，且根目录下不存在 logo.png 作为默认封面")

    # 2. 读取 html 内容
    with open(html_filepath, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 3. 微信接口操作
    token = get_access_token(account_config["appid"], account_config["secret"])
    
    # 替换正文配图为微信 URL
    final_html = replace_local_images_with_wechat_urls(html_content, token)
    
    # 上传封面图
    cover_media_id = upload_cover_image(cover_path, token)
    
    # 创建草稿箱
    draft_media_id = create_draft(token, title, "AI 架构师", digest, final_html, cover_media_id)
    
    # 获取预览链接
    draft_url = get_draft_url(token, draft_media_id)
    
    # 保存草稿信息到 .draft.json
    save_draft_info(md_filepath, draft_media_id, draft_url)
    
    result = {
        "media_id": draft_media_id,
        "url": draft_url,
        "publish_id": None
    }
    
    # 4. 执行正式发布（可选）
    if publish_mode == "自动保存草稿并正式发布":
        publish_id = publish_draft(token, draft_media_id)
        result["publish_id"] = publish_id

    return result
