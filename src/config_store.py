"""统一配置/指标存储层：config.json 与 indicators.json 的读写、代理环境变量构造。

供 app.py（视图层）、scheduler.py、zsxq_client.py 等共享，消除各模块重复实现。
所有路径基于进程 cwd（start 脚本保证 cwd=项目根目录）。
"""
import os
import json
from datetime import datetime

CONFIG_FILE = os.path.join("config", "config.json")
INDICATORS_FILE = os.path.join("config", "indicators.json")


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


def get_exec_env():
    env = os.environ.copy()
    try:
        cfg = load_config()
        proxy = cfg.get("network_proxy", "").strip()
        if proxy:
            env["HTTP_PROXY"] = proxy
            env["HTTPS_PROXY"] = proxy
            env["http_proxy"] = proxy
            env["https_proxy"] = proxy
    except Exception:
        pass
    return env


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
