#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtchair —— 荣泰(Rotai) RT7709S 按摩椅 · 自定义程序控制台

原理：荣泰智能 App 对 RT7709S 这类 Wi-Fi 机型不走蓝牙，而是把控制指令
POST 到荣泰 IoT 云：https://iot3.xingzhuo.xyz/api/bodydata/v1/iot
本脚本复用手机 App 里已登录的 token 和按摩椅 MAC，直接对云端下发
{"action":"SetDeviceProperty","params":{"Items":{属性:值}}}，
因此可以按秒级时间线任意编排官方 App 没有的按摩程序。

用法：
  python3 rtchair.py setup          # 从已连接的手机里提取 token / MAC
  python3 rtchair.py status         # 查看按摩椅状态
  python3 rtchair.py auto 椅上瑜伽   # 启动官方自动程序
  python3 rtchair.py on / off       # 开机 / 关机
  python3 rtchair.py set 手法=指压 力度=3 速度=2
  python3 rtchair.py run programs/久坐救星.plan     # 运行自定义时间线
  python3 rtchair.py serve          # 手机浏览器控制面板 http://<电脑IP>:8770
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime

API_URL = "https://iot3.xingzhuo.xyz/api/bodydata/v1/iot"
STATUS_URL = "https://iot3.xingzhuo.xyz/api/bodydata/v1/device/status"
APP_PKG = "com.rotai.intelligence"
DEFAULT_PORT = 8770

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "rtchair")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


# --------------------------------------------------------------------------
# 属性目录（来自 APK assets/config/RT7709S.json 与云端 ReturnStatus 实测）
# --------------------------------------------------------------------------
# values: {数值: 显示名}；aliases: 中文/英文别名
CATALOG = {
    "ChairSwitch": {
        "label": "电源", "values": {0: "关", 1: "开"},
        "aliases": ["电源", "开关", "power"],
    },
    "ChairPause": {
        "label": "暂停", "values": {0: "继续", 1: "暂停"},
        "aliases": ["暂停", "pause"],
    },
    "ProgramAuto": {
        "label": "自动程序",
        "values": {
            0: "无（手动模式）",
            16: "椅上瑜伽", 17: "脑力唤醒", 18: "放松冥想", 19: "总裁尊享",
            20: "女王尊享", 21: "乐龄尊享", 22: "颈肩舒缓", 23: "脊背呵护",
            24: "腰臀运动", 25: "清晨活力", 26: "午间小憩", 27: "良宵甜梦",
        },
        "aliases": ["程序", "自动程序", "auto"],
    },
    "SettingMassageSkill": {
        "label": "手法",
        "values": {0: "—", 1: "揉捏", 2: "敲击", 3: "揉敲", 4: "叩击", 5: "指压", 8: "深度指压"},
        "aliases": ["手法", "skill"],
    },
    "SettingMassageTime": {
        "label": "时长(分钟)",
        "values": {1: "10分钟", 2: "20分钟", 3: "30分钟"},
        "aliases": ["时长", "时间", "时长分钟", "time"],
    },
    "SettingStrength3D": {
        "label": "3D力度",
        "values": {0: "关", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
        "aliases": ["力度", "3d", "强度", "strength"],
    },
    "SettingStrengthAirBag": {
        "label": "气囊力度",
        "values": {0: "关", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5"},
        "aliases": ["气囊力度", "airbag_strength"],
    },
    "SettingSpeedMotor": {
        "label": "机芯速度",
        "values": {0: "—", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6"},
        "aliases": ["速度", "机芯速度", "speed"],
    },
    "SettingSpeedWheel": {
        "label": "脚底滚轮",
        "values": {0: "关", 1: "1", 2: "2", 3: "3"},
        "aliases": ["滚轮", "脚底滚轮", "wheel"],
    },
    "SettingStaWheel": {
        "label": "足部滚轮状态",
        "values": {0: "关", 1: "开"},
        "aliases": ["滚轮开关"],
    },
    "SettingMotorPosition": {
        "label": "机芯部位",
        "values": {0: "—", 1: "全程", 2: "局部", 3: "定点"},
        "aliases": ["部位", "区域", "position"],
    },
    "SettingHeatBack": {
        "label": "背部加热",
        "values": {0: "关", 1: "1档", 2: "2档", 3: "3档"},
        "aliases": ["背热", "背部加热", "heat_back"],
    },
    "SettingHeatShank": {
        "label": "小腿加热",
        "values": {0: "关", 1: "1档", 2: "2档", 3: "3档"},
        "aliases": ["腿热", "小腿加热", "heat_shank"],
    },
    "SettingAllAirBag": {
        "label": "全身气囊", "values": {0: "关", 1: "开"},
        "aliases": ["全身气囊"],
    },
    "SettingShoulderAirBag": {
        "label": "臂肩气囊", "values": {0: "关", 1: "开"},
        "aliases": ["臂肩气囊", "肩气囊"],
    },
    "SettingWaistAirBag": {
        "label": "背腰气囊", "values": {0: "关", 1: "开"},
        "aliases": ["背腰气囊", "腰气囊"],
    },
    "SettingHipAirBag": {
        "label": "臀部气囊", "values": {0: "关", 1: "开"},
        "aliases": ["臀部气囊", "臀气囊"],
    },
    "SettingShankAirBag": {
        "label": "小腿气囊", "values": {0: "关", 1: "开"},
        "aliases": ["小腿气囊", "腿气囊"],
    },
    "SettingZeroGravity": {
        "label": "零重力", "values": {0: "关", 1: "开"},
        "aliases": ["零重力", "zerog"],
    },
    "SettingBackrestControl": {
        "label": "靠背升降", "values": {0: "停止", 1: "升", 2: "降"},
        "aliases": ["靠背", "背升降"],
    },
    "SettingLegControl": {
        "label": "小腿升降", "values": {0: "停止", 1: "升", 2: "降"},
        "aliases": ["腿升降", "小腿升降"],
    },
    "SettingShankControl": {
        "label": "小腿伸缩", "values": {0: "停止", 1: "伸", 2: "缩"},
        "aliases": ["小腿伸缩"],
    },
    "SettingKneeControl": {
        "label": "膝盖伸缩", "values": {0: "停止", 1: "伸", 2: "缩"},
        "aliases": ["膝盖伸缩", "膝伸缩"],
    },
    "SettingMotorControl": {
        "label": "下机芯上下行", "values": {0: "停止", 1: "上行", 2: "下行"},
        "aliases": ["机芯上下"],
    },
}

# 反向索引：显示名/别名 -> 属性名
_ALIAS_TO_KEY = {}
for _k, _v in CATALOG.items():
    _ALIAS_TO_KEY[_k.lower()] = _k
    for _a in _v.get("aliases", []):
        _ALIAS_TO_KEY[_a.lower()] = _k

# 状态里常见但只读的属性中文名（云端不返回 Name 时兜底）
READONLY_LABELS = {
    "ChairStatus": {0: "关机", 1: "工作/复位", 2: "待机", 3: "运行中"},
    "ProgramCustom": "定制按摩",
    "ModuleRSSI": "Wi-Fi 信号",
    "ModuleIP": "公网 IP",
    "ModuleMAC": "MAC",
    "Model": "型号代码",
    "ModuleVersion": "固件版本",
    "ChairRunTime": "已运行(秒)",
    "ShouldIsCheck": "肩位检测",
    "ShouldIsAdjust": "肩位可调",
    "SettingHeatAll": "全身加热",
    "SettingMotorDirection": "揉捏方向",
    "SettingLegControl": "小腿升降",
    "SettingMotorControl": "下机芯上下行",
    "SettingBackrestControl": "靠背升降",
    "SettingKneeControl": "膝盖伸缩",
    "SettingShankControl": "小腿伸缩",
    "WifiModuleType": "Wi-Fi 模块类型",
    "BleMAC": "蓝牙 MAC",
    "ModuleWiFi": "Wi-Fi 连接",
    "ProgramSpecial": "特色按摩",
    "SettingTempMassageTime": "临时时长",
}

SAFE_STOP_PROPS = {"ChairPause": 1}


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["token"] = os.environ.get("RT_TOKEN") or cfg.get("token")
    cfg["mac"] = os.environ.get("RT_MAC") or cfg.get("mac")
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.chmod(CONFIG_PATH, 0o600)


# --------------------------------------------------------------------------
# 云端 API
# --------------------------------------------------------------------------
class ChairError(RuntimeError):
    pass


class Chair:
    def __init__(self, token, mac, timeout=15):
        self.token = token
        self.mac = mac
        self.timeout = timeout

    def _post(self, url, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("token", self.token)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("User-Agent", "rtchair/1.0")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise ChairError(f"HTTP {e.code}: {body[:200]}")
        except urllib.error.URLError as e:
            raise ChairError(f"网络错误: {e.reason}")
        try:
            js = json.loads(body)
        except Exception:
            raise ChairError(f"返回不是 JSON: {body[:200]}")
        if js.get("code") != 0:
            raise ChairError(f"云端返回 code={js.get('code')} {js.get('message')}")
        return js.get("data") or {}

    def set(self, items):
        """下发一组属性；items: {属性: 数值}"""
        return self._post(API_URL, {
            "mac": self.mac,
            "action": "SetDeviceProperty",
            "params": {"Items": items},
        })

    def query(self):
        data = self._post(API_URL, {"mac": self.mac, "action": "QueryDevicePropertyStatus"})
        out = {}
        for item in data.get("statusInfo", []):
            ident = item.get("Identifier")
            if not ident:
                continue
            val = item.get("Value")
            out[ident] = {
                "value": val,
                "name": item.get("Name") or ident,
                "unit": item.get("Unit") or "",
                "time": item.get("Time"),
            }
        return out

    def online(self):
        """GET /api/bodydata/v1/device/status?mac=... 判断云端是否在线"""
        req = urllib.request.Request(f"{STATUS_URL}?mac={self.mac}", method="GET")
        req.add_header("token", self.token)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))


class LocalChair:
    """离线模式：通过路由器上的假阿里云 broker 控制（不出家门）"""

    def __init__(self, base="http://192.168.1.1:8891", mac=""):
        self.base = base.rstrip("/")
        self.mac = mac

    def _req(self, path, obj=None, timeout=8):
        url = self.base + path
        if obj is None:
            req = urllib.request.Request(url, method="GET")
        else:
            req = urllib.request.Request(url, data=json.dumps(obj, ensure_ascii=False).encode(),
                                        method="POST")
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise ChairError(f"本地 broker HTTP {e.code}: {e.read()[:200]}")
        except urllib.error.URLError as e:
            raise ChairError(f"连不上本地 broker（{self.base}）：{e.reason}")

    def set(self, items):
        items = {k: int(v) for k, v in items.items()}
        r = self._req("/set", items)
        if not r.get("ok"):
            raise ChairError(f"本地 broker 返回失败: {r}")
        return r

    def query(self):
        st = self._req("/status")
        props = st.get("props") or {}
        out = {}
        for k, v in props.items():
            out[k] = {"value": str(v), "name": CATALOG.get(k, {}).get("label", k),
                      "unit": "", "time": None}
        return out

    def online(self):
        try:
            return bool(self._req("/status").get("connected"))
        except ChairError:
            return False


def chair_from_config(args=None):
    cfg = load_config()
    mode = getattr(args, "mode", None) or cfg.get("mode") or "cloud"
    broker = getattr(args, "broker", None) or cfg.get("broker") or "http://192.168.1.1:8891"
    if mode == "local":
        return LocalChair(broker, cfg.get("mac") or "")
    token = getattr(args, "token", None) or cfg.get("token")
    mac = getattr(args, "mac", None) or cfg.get("mac")
    if not token or not mac:
        sys.exit("未配置 token / mac，请先运行：python3 rtchair.py setup")
    return Chair(token, mac)


def cmd_mode(args):
    cfg = load_config()
    if args.value:
        cfg["mode"] = args.value
        if args.broker:
            cfg["broker"] = args.broker
        cfg.setdefault("broker", "http://192.168.1.1:8891")
        save_config(cfg)
    print(f"当前模式: {cfg.get('mode', 'cloud')}"
          + (f"   本地 broker: {cfg.get('broker')}" if cfg.get("mode") == "local" else ""))


# --------------------------------------------------------------------------
# 解析「属性=值」
# --------------------------------------------------------------------------
def resolve_key(text):
    k = _ALIAS_TO_KEY.get(text.strip().lower())
    if k:
        return k
    for name in CATALOG:
        if name.lower() == text.strip().lower():
            return name
    raise ChairError(f"未知属性: {text}")


def resolve_value(key, raw):
    raw = str(raw).strip()
    low = raw.lower()
    if low in ("开", "on", "true"):
        return 1
    if low in ("关", "off", "false"):
        return 0
    m = re.fullmatch(r"-?\d+", raw)
    if m:
        return int(raw)
    values = CATALOG[key].get("values", {})
    for num, label in values.items():
        if str(label) == raw:
            return num
    # 允许「3档」「10分」这类写法
    m = re.search(r"(\d+)", raw)
    if m and int(m.group(1)) in values:
        return int(m.group(1))
    raise ChairError(f"{CATALOG[key]['label']} 不认识的值: {raw}（可选：{value_hint(key)}）")


def value_hint(key):
    values = CATALOG[key].get("values", {})
    return " / ".join(f"{v}={label}" for v, label in values.items())


AIRBAG_MAP = {
    "全身": "SettingAllAirBag", "臂肩": "SettingShoulderAirBag", "肩": "SettingShoulderAirBag",
    "背腰": "SettingWaistAirBag", "腰": "SettingWaistAirBag", "臀部": "SettingHipAirBag",
    "臀": "SettingHipAirBag", "腿脚": "SettingShankAirBag", "小腿": "SettingShankAirBag",
}
AIRBAG_ALL = ["SettingAllAirBag", "SettingShoulderAirBag", "SettingWaistAirBag",
              "SettingHipAirBag", "SettingShankAirBag"]


def resolve_assign(key_text, value_text):
    """把 键=值 解析成需要下发的 {属性: 数值}，可能是一个或多个属性"""
    k = key_text.strip()
    v = str(value_text).strip()
    if k.lower() in ("气囊", "airbag"):
        if v in ("关", "off", "0", "全部关"):
            return {p: 0 for p in AIRBAG_ALL}
        if v in ("全身", "开", "on", "1"):
            return {"SettingAllAirBag": 1}
        if v in AIRBAG_MAP:
            return {AIRBAG_MAP[v]: 1}
        raise ChairError(f"气囊不认识的值: {v}（全身/臂肩/背腰/臀部/腿脚/关）")
    key = resolve_key(k)
    if key == "SettingMassageTime":
        if v in ("10", "20", "30"):
            return {key: {"10": 1, "20": 2, "30": 3}[v]}
        if v in ("10分钟", "20分钟", "30分钟"):
            return {key: {"10分钟": 1, "20分钟": 2, "30分钟": 3}[v]}
    return {key: resolve_value(key, v)}


def parse_assignments(tokens):
    """把 ['手法=指压','力度=3'] 或 ['手法','指压'] 解析成 {key: int}"""
    items = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if "=" in tok:
            k, v = tok.split("=", 1)
            items.update(resolve_assign(k, v))
            i += 1
        else:
            if i + 1 >= len(tokens):
                raise ChairError(f"孤立的参数: {tok}")
            items.update(resolve_assign(tok, tokens[i + 1]))
            i += 2
    return items


# --------------------------------------------------------------------------
# 时间线
# --------------------------------------------------------------------------
class Step:
    __slots__ = ("at", "actions", "line_no", "raw")

    def __init__(self, at, actions, line_no, raw):
        self.at = at
        self.actions = actions
        self.line_no = line_no
        self.raw = raw


def parse_time(text):
    text = text.strip()
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", text)
    if m:
        h = int(m.group(1) or 0)
        return h * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.fullmatch(r"(\d+):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|秒)?", text)
    if m:
        return float(m.group(1))
    raise ChairError(f"看不懂的时间: {text}")


def parse_plan(text):
    steps = []
    meta = {"name": "", "desc": ""}
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("# ").strip()
            if ":" in body:
                k, v = body.split(":", 1)
                k, v = k.strip(), v.strip()
                if k in ("名称", "name"):
                    meta["name"] = v
                elif k in ("说明", "desc", "description"):
                    meta["desc"] = v
                else:
                    meta["desc"] = (meta["desc"] + " " + body).strip()
            elif body:
                meta["desc"] = (meta["desc"] + " " + body).strip()
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            raise ChairError(f"第{no}行格式应为「时间 指令」: {raw}")
        at = parse_time(parts[0])
        try:
            actions = parse_actions(parts[1])
        except ChairError as e:
            raise ChairError(f"第{no}行：{e}")
        steps.append(Step(at, actions, no, raw))
    steps.sort(key=lambda s: s.at)
    return meta, steps


def parse_actions(text):
    """一行动作：开机 / 关机 / 暂停 / 继续 / 程序=椅上瑜伽 / 手法=揉捏 力度=3 ..."""
    tokens = [t for t in re.split(r"[\s,，、]+", text.strip()) if t]
    actions = []
    assigns = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if tok in ("开机", "on"):
            actions.append(("set", {"ChairSwitch": 1}))
            i += 1
        elif tok in ("关机", "off"):
            actions.append(("set", {"ChairSwitch": 0}))
            i += 1
        elif tok in ("暂停", "pause"):
            actions.append(("set", {"ChairPause": 1}))
            i += 1
        elif tok in ("继续", "resume"):
            actions.append(("set", {"ChairPause": 0}))
            i += 1
        elif tok in ("状态", "status"):
            actions.append(("status", None))
            i += 1
        elif "=" in tok:
            k, v = tok.split("=", 1)
            assigns.update(resolve_assign(k, v))
            i += 1
        elif low in ("气囊", "airbag") or low in _ALIAS_TO_KEY:
            if i + 1 >= len(tokens):
                raise ChairError(f"{tok} 缺少取值")
            assigns.update(resolve_assign(tok, tokens[i + 1]))
            i += 2
        else:
            raise ChairError(f"看不懂的指令: {tok}")
    if assigns:
        actions.append(("set", assigns))
    return actions


def fmt_ts(sec):
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def run_plan(chair, steps, meta, dry_run=False, on_event=None, stop_event=None):
    t0 = time.time()
    for step in steps:
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt
        delay = step.at - (time.time() - t0)
        if dry_run:
            print(f"  [{fmt_ts(step.at)}] {step.raw.strip()}")
            delay = 0
        if delay > 0:
            if on_event:
                on_event("wait", {"until": step.at, "raw": step.raw})
            end = time.time() + delay
            while time.time() < end:
                if stop_event is not None and stop_event.is_set():
                    raise KeyboardInterrupt
                time.sleep(min(0.5, end - time.time()))
        for kind, payload in step.actions:
            if kind == "set":
                if dry_run:
                    if on_event:
                        on_event("set", {"props": payload, "raw": step.raw})
                else:
                    chair.set(payload)
                    if on_event:
                        on_event("set", {"props": payload, "raw": step.raw})
                    time.sleep(0.35)
            elif kind == "status":
                st = chair.query()
                if on_event:
                    on_event("status", st)
    if on_event:
        on_event("done", None)


def describe(ident, val):
    """把属性值翻译成中文显示名，返回 (显示文本, 是否已知)"""
    cat = CATALOG.get(ident)
    if cat and str(val).isdigit():
        v = int(val)
        if v in cat.get("values", {}):
            return str(cat["values"][v]), True
    ro = READONLY_LABELS.get(ident)
    if isinstance(ro, dict) and str(val).isdigit() and int(val) in ro:
        return ro[int(val)], True
    return str(val), False


HIDDEN_DEFAULT = {"ModuleIP", "ModuleMAC", "BleMAC", "ModuleVersion", "Model",
                  "ModuleRSSI", "WifiModuleType", "ProgramCustom", "ProgramSpecial",
                  "ShouldIsCheck", "ShouldIsAdjust"}


def cmd_status(args, chair=None):
    chair = chair or chair_from_config(args)
    st = chair.query()
    cfg = load_config()
    print(f"荣泰 {cfg.get('model') or ''} · {chair.mac or ''}   {datetime.now():%H:%M:%S}")
    print("-" * 56)
    if not st and isinstance(chair, LocalChair):
        print("  （椅子已连上 broker，但还没上报状态；发一条指令或等几秒再查）")
    order = list(CATALOG)
    for ident in sorted(st, key=lambda k: (CATALOG.get(k, {}).get("label") is None,
                                           order.index(k) if k in CATALOG else 0, k)):
        info = st[ident]
        val = info["value"]
        if val is None:
            continue
        if not getattr(args, "verbose", False) and ident in HIDDEN_DEFAULT:
            continue
        text, known = describe(ident, val)
        unit = info.get("unit") or ""
        label = info.get("name") or ident
        line = f"  {label:<14} {text}"
        if unit and known is False:
            line += f" {unit}"
        if getattr(args, "verbose", False):
            line += f"   [{ident}={val}]"
        print(line)
    return st


# --------------------------------------------------------------------------
# setup：从手机 adb 备份中提取 token 与按摩椅 MAC
# --------------------------------------------------------------------------
def read_adb_backup(path):
    with open(path, "rb") as f:
        blob = f.read()
    parts = []
    idx = 0
    for _ in range(4):
        j = blob.index(b"\n", idx)
        parts.append(blob[idx:j])
        idx = j + 1
    compressed = parts[2].strip() == b"1"
    raw = zlib.decompress(blob[idx:]) if compressed else blob[idx:]
    return raw


def parse_backup_files(raw):
    """极简 tar 解析，返回 {名字: bytes}"""
    out = {}
    pos = 0
    n = len(raw)
    while pos + 512 <= n:
        header = raw[pos:pos + 512]
        if header[:1] == b"\0":
            break
        name = header[0:100].split(b"\0", 1)[0].decode("utf-8", "replace")
        prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8", "replace")
        if prefix:
            name = prefix + "/" + name
        try:
            size = int(header[124:136].split(b"\0", 1)[0].strip() or b"0", 8)
        except ValueError:
            size = 0
        typ = header[156:157]
        pos += 512
        data = raw[pos:pos + size]
        pos += (size + 511) // 512 * 512
        if typ in (b"0", b"\0"):
            out[name] = data
    return out


def extract_credentials(files):
    """从备份文件集合里取 token 和按摩椅信息（Room 数据库要注意 WAL 文件）"""
    token = mac = model = None
    for name, data in files.items():
        if name.endswith("sp/com.rotai.intelligence.xml"):
            text = data.decode("utf-8", "replace")
            m = re.search(r'name="user_tokenrelease">([^<]+)<', text)
            if m:
                token = m.group(1)

    db_items = {os.path.basename(n): d for n, d in files.items()
                if "room_intelligence.db" in n}
    if db_items:
        tmpdir = tempfile.mkdtemp(prefix="rtchair_db_")
        try:
            for fn, data in db_items.items():
                with open(os.path.join(tmpdir, fn), "wb") as f:
                    f.write(data)
            import sqlite3
            con = sqlite3.connect(os.path.join(tmpdir, "room_intelligence.db"))
            try:
                row = con.execute(
                    "select title, mac, type, protocolType from connected_device "
                    "order by is_default desc, updateTime desc limit 1").fetchone()
                if row:
                    model, mac, _, _ = row
            finally:
                con.close()
        finally:
            for fn in os.listdir(tmpdir):
                try:
                    os.unlink(os.path.join(tmpdir, fn))
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass

    # 兜底：数据库里直接扫 12 位十六进制 MAC
    if not mac:
        for name, data in files.items():
            if "room_intelligence.db" not in name:
                continue
            for m in re.finditer(rb"[0-9A-Fa-f]{12}", data):
                cand = m.group(0).decode()
                if cand.upper().startswith(("40", "48", "68", "C8", "E0", "F0", "AC", "DC")):
                    mac = cand.upper()
                    break
    return token, mac, model


def cmd_setup(args):
    adb = args.adb or shutil.which("adb") or os.path.join(
        os.path.expanduser("~"), "Android/Sdk/platform-tools/adb")
    if not os.path.exists(adb):
        sys.exit("找不到 adb，请用 --adb 指定，或手动 --token/--mac")
    backup = os.path.join(tempfile.gettempdir(), "rtchair_backup.ab")
    if os.path.exists(backup):
        os.unlink(backup)
    print("=" * 62)
    print("即将用 adb 备份荣泰智能 App 的数据（只读，用于提取登录 token 与按摩椅 MAC）")
    print("请在弹出的手机上点「备份我的数据」（不要输入密码）：")
    print("=" * 62)
    proc = subprocess.run([adb, "backup", "-f", backup, "-noapk", APP_PKG])
    if not os.path.exists(backup) or os.path.getsize(backup) == 0:
        sys.exit("备份失败或未确认。请解锁手机后重试。")
    files = parse_backup_files(read_adb_backup(backup))
    token, mac, model = extract_credentials(files)
    if not token or not mac:
        sys.exit(f"提取失败：token={bool(token)} mac={bool(mac)}")
    cfg = {"token": token, "mac": mac, "model": model or "", "saved_at": datetime.now().isoformat()}
    save_config(cfg)
    print(f"\n✔ 已保存到 {CONFIG_PATH}")
    print(f"  token : {token}")
    print(f"  mac   : {mac}  ({model or '未知型号'})")
    chair = Chair(token, mac)
    try:
        data = chair.query()
        print(f"  ✔ 云端连通，当前共 {len(data)} 个状态项")
    except ChairError as e:
        print(f"  ✘ 云端测试失败: {e}")


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
def cmd_set(args, chair=None):
    chair = chair or chair_from_config(args)
    items = parse_assignments(args.assign)
    if not items:
        sys.exit("没有可下发的属性")
    chair.set(items)
    pretty = "，".join(f"{CATALOG.get(k, {}).get('label', k)}={v}" for k, v in items.items())
    print(f"✔ 已下发：{pretty}")


def cmd_auto(args, chair=None):
    chair = chair or chair_from_config(args)
    key = "ProgramAuto"
    val = resolve_value(key, args.program)
    chair.set({key: val})
    print(f"✔ 启动自动程序：{CATALOG[key]['values'].get(val, val)}（{val}）")


def cmd_switch(args, chair=None):
    chair = chair or chair_from_config(args)
    val = 1 if args.action == "on" else 0
    chair.set({"ChairSwitch": val})
    print("✔ 已开机" if val else "✔ 已关机")


def cmd_run(args, chair=None):
    chair = chair or chair_from_config(args)
    with open(args.plan, "r", encoding="utf-8") as f:
        text = f.read()
    meta, steps = parse_plan(text)
    name = meta.get("name") or os.path.basename(args.plan)
    print(f"▶ 运行程序：{name}（{len(steps)} 个步骤）")
    if meta.get("desc"):
        print(f"  {meta['desc']}")
    print("-" * 58)
    last = [0.0]

    def on_event(kind, payload):
        if kind == "set":
            pretty = "，".join(
                f"{CATALOG.get(k, {}).get('label', k)}={CATALOG.get(k, {}).get('values', {}).get(v, v)}"
                for k, v in payload["props"].items())
            print(f"  {int(time.time() - last[0]) if last[0] else 0:>4}s  {pretty}")
        elif kind == "done":
            print("-" * 58)
            print("✔ 程序执行完毕")

    if args.dry_run:
        on_event = lambda *a: None
    last[0] = time.time()
    try:
        run_plan(chair, steps, meta, dry_run=args.dry_run, on_event=on_event)
    except KeyboardInterrupt:
        print("\n已中断（按摩椅保持当前状态）。如需关机：python3 rtchair.py off")


# --------------------------------------------------------------------------
# Web 控制面板
# --------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>荣泰按摩椅 · 自定义程序</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#232b36;--txt:#e6edf3;--dim:#8b949e;--acc:#3b82f6;--ok:#22c55e;--warn:#f59e0b}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 -apple-system,"PingFang SC","Noto Sans SC",sans-serif;padding:16px 14px 60px}
h1{font-size:18px;margin:0 0 2px}
.sub{color:var(--dim);font-size:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 0;font-size:14px}
.row .k{color:var(--dim)}
.badge{font-size:11px;padding:2px 8px;border-radius:99px;background:#1f2937;color:var(--dim)}
.badge.on{background:rgba(34,197,94,.15);color:var(--ok)}
button{font:inherit;border:1px solid var(--line);background:#21262d;color:var(--txt);border-radius:10px;padding:9px 12px;cursor:pointer;white-space:nowrap}
button:active{transform:scale(.98)}
button.primary{background:var(--acc);border-color:var(--acc)}
button.danger{background:#7f1d1d;border-color:#991b1b}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.prog{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px}
.prog>div{flex:1;min-width:0}
.prog button{flex:0 0 auto;align-self:center}
.prog:last-child{border-bottom:0}
.prog .t{font-weight:500}
.prog .d{color:var(--dim);font-size:12px}
textarea{width:100%;min-height:180px;background:#0b0f14;color:#c9d1d9;border:1px solid var(--line);border-radius:10px;padding:10px;font:12px/1.6 ui-monospace,Menlo,monospace;resize:vertical}
#log{font:12px/1.6 ui-monospace,Menlo,monospace;color:var(--dim);white-space:pre-wrap;max-height:180px;overflow:auto}
.pill{display:inline-block;padding:5px 10px;margin:0 6px 6px 0;border:1px solid var(--line);border-radius:99px;font-size:13px}
.pill:active,.pill.sel{background:var(--acc);border-color:var(--acc)}
.row2{display:flex;gap:8px;flex-wrap:wrap}
</style></head><body>
<h1>荣泰按摩椅</h1><div class="sub" id="dev">连接中…</div>

<div class="card">
  <div class="row"><span class="k">状态</span><span id="s-state" class="badge">—</span></div>
  <div class="row"><span class="k">手法 / 力度</span><span id="s-skill">—</span></div>
  <div class="row"><span class="k">速度 / 部位</span><span id="s-speed">—</span></div>
  <div class="row"><span class="k">时长 / 剩余</span><span id="s-time">—</span></div>
  <div class="row"><span class="k">加热 / 气囊</span><span id="s-heat">—</span></div>
  <div class="row2" style="margin-top:10px">
    <button class="primary" onclick="api('/api/set',{ChairSwitch:1})">开机</button>
    <button onclick="api('/api/set',{ChairPause:1})">暂停</button>
    <button onclick="api('/api/set',{ChairPause:0})">继续</button>
    <button class="danger" onclick="powerOff()">关机</button>
  </div>
</div>

<div class="card">
  <div class="row"><span class="k">官方自动程序</span></div>
  <div id="autos" class="row2"></div>
</div>

<div class="card">
  <div class="row"><span class="k">我的自定义程序</span><span class="badge">本机运行</span></div>
  <div id="programs"></div>
  <div id="runstate" class="sub" style="margin:8px 0 0"></div>
</div>

<div class="card">
  <div class="row"><span class="k">快速调节</span></div>
  <div class="row2" id="quick"></div>
</div>

<div class="card">
  <div class="row"><span class="k">自定义时间线</span></div>
  <div class="sub" style="margin:4px 0 8px">格式：<code>分:秒 指令</code>，指令支持 开机/关机/暂停/继续、时长=30、手法=指压、力度=3、速度=2、部位=局部、背热=2、气囊=全身、零重力=开…</div>
  <textarea id="plan" spellcheck="false"></textarea>
  <div class="row2" style="margin-top:8px">
    <button class="primary" onclick="runCustom()">▶ 运行</button>
    <button onclick="loadExample()">载入示例</button>
    <button class="danger" onclick="stopPlan()">停止</button>
  </div>
</div>

<div class="card"><div class="row"><span class="k">日志</span></div><div id="log"></div></div>

<script>
const $=s=>document.querySelector(s);
let lastPlanTimer=null;
function log(t){const el=$('#log');el.textContent=t+"\n"+el.textContent.slice(0,1500)}
async function api(path,body){
  try{
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
    const j=await r.json();
    if(j.error) log('✘ '+j.error); else log('✔ '+JSON.stringify(j));
    setTimeout(refresh,400);
  }catch(e){log('✘ '+e)}
}
async function powerOff(){ if(confirm('确定关机？')) api('/api/set',{ChairSwitch:0}) }
async function refresh(){
  try{
    const j=await (await fetch('/api/status')).json();
    if(j.error){$('#s-state').textContent='离线';$('#s-state').className='badge';return}
    const st=j.status||{};
    const g=(k)=>{const x=st[k];return x?x.value:null};
    $('#dev').textContent=(j.model||'')+' · '+j.mac;
    const map={0:'关机',1:'运行',2:'待机',3:'运行中'};
    const stv=g('ChairStatus');
    $('#s-state').textContent=map[stv]??('状态'+stv);
    $('#s-state').className='badge '+(stv==1||stv==3?'on':'');
    const sk=v=>j.skills?.[v]??v;
    $('#s-skill').textContent=sk(g('SettingMassageSkill'))+' / '+g('SettingStrength3D');
    $('#s-speed').textContent=g('SettingSpeedMotor')+' / '+(j.positions?.[g('SettingMotorPosition')]??g('SettingMotorPosition'));
    $('#s-time').textContent=(j.times?.[g('SettingMassageTime')]??'—')+' / '+(g('ChairRunTime')??'—')+'s';
    $('#s-heat').textContent='背'+(g('SettingHeatBack')??0)+' 腿'+(g('SettingHeatShank')??0)+' · 气囊'+(g('SettingStrengthAirBag')??0);
  }catch(e){}
}
function fillAutos(list){
  const box=$('#autos'); box.innerHTML='';
  list.forEach(p=>{const b=document.createElement('button');b.className='pill';b.textContent=p.name;b.onclick=()=>api('/api/set',{ChairSwitch:1,ProgramAuto:p.value});box.appendChild(b)});
}
async function loadPrograms(){
  const j=await (await fetch('/api/programs')).json();
  const box=$('#programs');box.innerHTML='';
  (j.programs||[]).forEach(p=>{
    const d=document.createElement('div');d.className='prog';
    d.innerHTML=`<div><div class="t">${p.name}</div><div class="d">${p.desc||''} · ${p.steps}步</div></div>`;
    const b=document.createElement('button');b.className='primary';b.textContent='▶ 运行';
    b.onclick=()=>{log('▶ '+p.name);fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan:p.plan})})};
    d.appendChild(b);box.appendChild(d);
  });
  if(!(j.programs||[]).length) box.innerHTML='<div class="sub">programs/ 目录下还没有 .plan 文件</div>';
}
async function runCustom(){
  const plan=$('#plan').value.trim();
  if(!plan) return log('时间线为空');
  const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plan})});
  const j=await r.json(); log(j.error?('✘ '+j.error):'▶ 已开始自定义程序');
  pollRun();
}
async function stopPlan(){ await fetch('/api/stop',{method:'POST'}); log('■ 已停止'); }
function pollRun(){
  clearInterval(lastPlanTimer);
  lastPlanTimer=setInterval(async()=>{
    const j=await (await fetch('/api/run')).json();
    $('#runstate').textContent=j.running?('运行中：'+(j.name||'')+' · 已执行 '+(j.elapsed||0)+'s'):(j.last?('上次：'+j.last):'');
    if(!j.running) clearInterval(lastPlanTimer);
    refresh();
  },1000);
}
function loadExample(){ $('#plan').value=`# 名称: 我的肩颈时间线\n00:00 开机\n00:03 时长=30 手法=揉捏 力度=3 速度=2 部位=全程 背热=2\n05:00 手法=指压 部位=局部\n10:00 气囊=全身 气囊力度=4\n20:00 手法=敲击 速度=1 力度=2\n29:00 关机`; }
function fillQuick(){
  const box=$('#quick');
  const defs=[['揉捏',{SettingMassageSkill:1}],['敲击',{SettingMassageSkill:2}],['叩击',{SettingMassageSkill:4}],['指压',{SettingMassageSkill:5}],
              ['力度+',{SettingStrength3D:4}],['力度-',{SettingStrength3D:2}],['零重力',{SettingZeroGravity:1}],['背热',{SettingHeatBack:2}],
              ['全身气囊',{SettingAllAirBag:1}],['气囊关',{SettingAllAirBag:0}],['10分钟',{SettingMassageTime:1}],['20分钟',{SettingMassageTime:2}]];
  defs.forEach(([n,v])=>{const b=document.createElement('button');b.className='pill';b.textContent=n;b.onclick=()=>api('/api/set',v);box.appendChild(b)});
}
(async function(){
  const cfg=await (await fetch('/api/config')).json();
  fillAutos(cfg.autos||[]); fillQuick(); loadPrograms(); refresh(); pollRun(); setInterval(refresh,3000);
})();
</script></body></html>"""


def make_handler(chair, cfg):
    from http.server import BaseHTTPRequestHandler

    state = {"thread": None, "stop": threading.Event(), "name": "", "t0": 0, "last": ""}

    def execute_plan(text):
        meta, steps = parse_plan(text)
        state["name"] = meta.get("name") or "自定义程序"
        state["t0"] = time.time()
        state["stop"].clear()

        def run():
            try:
                logs = []
                run_plan(chair, steps, meta, on_event=lambda k, p: logs.append((k, p)),
                         stop_event=state["stop"])
                state["last"] = f"{state['name']} 完成"
            except KeyboardInterrupt:
                state["last"] = f"{state['name']} 已停止"
            except Exception as e:
                state["last"] = f"{state['name']} 出错: {e}"
            finally:
                state["thread"] = None

        th = threading.Thread(target=run, daemon=True)
        state["thread"] = th
        th.start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, "application/json; charset=utf-8",
                       json.dumps(obj, ensure_ascii=False))

        def _read_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, "text/html; charset=utf-8", HTML_PAGE)
            if self.path == "/api/status":
                try:
                    st = chair.query()
                    return self._json({
                        "mac": chair.mac, "model": cfg.get("model", ""),
                        "status": {k: v for k, v in st.items()},
                        "skills": {str(k): v for k, v in CATALOG["SettingMassageSkill"]["values"].items()},
                        "positions": {str(k): v for k, v in CATALOG["SettingMotorPosition"]["values"].items()},
                        "times": {str(k): v for k, v in CATALOG["SettingMassageTime"]["values"].items()},
                    })
                except Exception as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/config":
                autos = [{"name": v, "value": k} for k, v in CATALOG["ProgramAuto"]["values"].items()]
                return self._json({"mac": chair.mac, "model": cfg.get("model", ""), "autos": autos})
            if self.path == "/api/programs":
                progs = []
                pdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programs")
                if os.path.isdir(pdir):
                    for fn in sorted(os.listdir(pdir)):
                        if not fn.endswith(".plan"):
                            continue
                        try:
                            with open(os.path.join(pdir, fn), "r", encoding="utf-8") as f:
                                text = f.read()
                            meta, steps = parse_plan(text)
                            progs.append({"name": meta.get("name") or fn, "desc": meta.get("desc", ""),
                                          "steps": len(steps), "plan": text})
                        except Exception:
                            continue
                return self._json({"programs": progs})
            if self.path == "/api/run":
                running = state["thread"] is not None and state["thread"].is_alive()
                return self._json({
                    "running": running, "name": state["name"],
                    "elapsed": int(time.time() - state["t0"]) if running else 0,
                    "last": state["last"],
                })
            self._send(404, "text/plain", "not found")

        def do_POST(self):
            body = self._read_json()
            if self.path == "/api/set":
                try:
                    items = {k: int(v) for k, v in body.items()}
                    chair.set(items)
                    return self._json({"ok": True, "sent": items})
                except Exception as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/run":
                try:
                    plan = body.get("plan") or ""
                    parse_plan(plan)  # 先校验
                    execute_plan(plan)
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/stop":
                state["stop"].set()
                return self._json({"ok": True})
            self._send(404, "text/plain", "not found")

    return Handler


def cmd_serve(args):
    from http.server import ThreadingHTTPServer

    chair = chair_from_config(args)
    cfg = load_config()
    Handler = make_handler(chair, cfg)
    port = args.port
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ip = local_ip()
    print(f"控制面板已启动： http://{ip}:{port}   (手机连同一 Wi-Fi 打开)")
    print("Ctrl+C 退出（不会改变按摩椅状态）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")


def local_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="荣泰 RT7709S 按摩椅自定义控制台（走荣泰 IoT 云）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--token", help="覆盖配置里的 token")
    ap.add_argument("--mac", help="覆盖配置里的按摩椅 MAC")
    ap.add_argument("--mode", choices=["cloud", "local"], help="控制通道：cloud=荣泰云 / local=局域网假云")
    ap.add_argument("--broker", help="local 模式下的 broker 地址，如 http://192.168.1.1:8891")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("setup", help="从手机 adb 备份中提取 token / MAC")
    p.add_argument("--adb", help="adb 可执行文件路径")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("status", help="查看状态")
    p.add_argument("-v", "--verbose", action="store_true", help="显示全部原始属性")
    p.set_defaults(func=cmd_status)
    sub.add_parser("on", help="开机").set_defaults(func=cmd_switch, action="on")
    sub.add_parser("off", help="关机").set_defaults(func=cmd_switch, action="off")

    p = sub.add_parser("set", help="设置属性，如：set 手法=指压 力度=3")
    p.add_argument("assign", nargs="+", help="属性=值 ...")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("auto", help="启动官方自动程序")
    p.add_argument("program", help="名称或编号，如 椅上瑜伽 / 16")
    p.set_defaults(func=cmd_auto)

    p = sub.add_parser("run", help="运行自定义时间线 .plan")
    p.add_argument("plan")
    p.add_argument("--dry-run", action="store_true", help="只打印不真的下发")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve", help="启动网页控制面板")
    p.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mode", help="查看/切换 cloud(荣泰云) 或 local(离线)")
    p.add_argument("value", nargs="?", choices=["cloud", "local"])
    p.add_argument("--broker", help="local 模式的 broker 地址")
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("props", help="列出可写属性与取值")
    p.set_defaults(func=lambda a: show_props())

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    args.func(args)


def show_props():
    for k, v in CATALOG.items():
        print(f"{k:<26} {v['label']:<8} " + "  ".join(f"{n}={l}" for n, l in v.get("values", {}).items()))


if __name__ == "__main__":
    main()
