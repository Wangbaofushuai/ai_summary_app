import os
import re
import fitz
from openai import OpenAI

import prompts

def call_chat_completion(client, model, messages, chan_config=None):
    kwargs = {
        "model": model,
        "messages": messages
    }
    if chan_config and isinstance(chan_config, dict):
        if chan_config.get("enable_thinking", False):
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            effort = chan_config.get("reasoning_effort", "high")
            if effort in ["high", "max"]:
                kwargs["reasoning_effort"] = effort
    return client.chat.completions.create(**kwargs)

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

def generate_summary(text, api_key, base_url, model, mode, custom_prompt=None, chan_config=None):
    if not api_key: return "未提供 API Key。"
    system_prompt = prompts.build_summary_system_prompt(mode)
    if mode == "个股分析": 
        system_prompt += "【当前任务】：深度个股价值分析，必须涵盖核心逻辑、业务拆解、估值及风险。重点指标必须用表格解构。"
    elif mode == "行业分析": 
        system_prompt += "【当前任务】：深度行业宏观趋势分析，涵盖宏观驱动力、产业链上下游剖析、市场竞争格局及展望。产业链和竞争格局环节必须强制使用表格排版。"
    else: 
        system_prompt += "【当前任务】：详尽总结分析，提取核心要点，将散乱的信息重构成逻辑极为清晰、带有丰富表格和加粗高亮的深度简报。"
    
    user_content = f"指令: {custom_prompt}\n\n待处理内容:\n{text}" if custom_prompt else text
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)
        response = call_chat_completion(client, model, [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], chan_config=chan_config)
        if not response.choices:
            return f"AI 总结失败: 接口返回空数据，可能是该模型({model})暂不支持或网络限流。详情: {response}"
        return response.choices[0].message.content
    except Exception as e: return f"AI 总结失败: {str(e)}"

