# -*- coding: utf-8 -*-
"""配置与日志。

配置文件：本工具目录下的 settings.json，按「图片文件夹」分别保存设置，
  下次打开同一文件夹自动恢复。不会往你的图片文件夹里写任何东西。
日志文件：本工具目录下的 logs/app.log，记录启动、打开文件夹、导出、错误等。
"""
import os
import json
import time
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "settings.json")
LOG_DIR = os.path.join(BASE, "logs")
LOG_PATH = os.path.join(LOG_DIR, "app.log")
LOG_MAX = 2 * 1024 * 1024      # 超过 2MB 轮转为 app.log.1

_lock = threading.Lock()


# ---------------- 日志 ----------------

def log(msg):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX:
            try:
                os.replace(LOG_PATH, LOG_PATH + ".1")
            except Exception:
                pass
        line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + str(msg) + "\n"
        with _lock:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def log_path():
    return LOG_PATH


# ---------------- 配置 ----------------

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"version": 1, "folders": {}}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return {"version": 1, "folders": {}}
        cfg.setdefault("version", 1)
        cfg.setdefault("folders", {})
        return cfg
    except Exception as e:
        log("读取配置失败，改用默认: " + repr(e))
        return {"version": 1, "folders": {}}


def save_config(cfg):
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except Exception as e:
        log("保存配置失败: " + repr(e))
        return False


def get_folder_cfg(cfg, folder):
    return (cfg.get("folders") or {}).get(folder)


def set_folder_cfg(cfg, folder, data):
    cfg.setdefault("folders", {})[folder] = data
    save_config(cfg)
