#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OTA 侦察工具（只读，不会触发升级）

用途：在不触发任何升级的前提下，摸清按摩椅固件的版本/升级通道。

用法：
  python3 tools/ota_watch.py --cloud          # 查云端设备状态/升级进度（只读 GET）
  python3 tools/ota_watch.py --broker-log     # 看假云 broker 日志里的升级类消息
  python3 tools/ota_watch.py --follow         # 持续监听 broker 日志（Ctrl+C 退出）

重要：**不要**调用 POST /api/bodydata/v1/firmware/upgrade —— 那会给椅子真正下发
升级指令（URL/md5/size），刷错就变砖。本工具只做只读侦察。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

CLOUD = "https://iot3.xingzhuo.xyz"
ROUTER = os.environ.get("ROUTER", "router")  # 改成你的路由器 SSH 别名
BROKER_LOG = "/tmp/local_cloud_broker.log"
KEYWORDS = ("upgrade", "Upgrade", "rrpc", "Service", "firmware", "ota", "OTA")


def load_cfg() -> dict:
    p = os.path.join(os.path.expanduser("~"), ".config", "rtchair", "config.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def get(path: str, token: str, timeout: float = 10) -> dict:
    req = urllib.request.Request(CLOUD + path, headers={"token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def cmd_cloud(_args) -> None:
    cfg = load_cfg()
    token, mac = cfg.get("token"), cfg.get("mac")
    if not token or not mac:
        sys.exit("未配置 token/mac，先运行 rtchair.py setup（或手工填 ~/.config/rtchair/config.json）")
    print(f"# 只读查询 {CLOUD} (mac={mac})")
    status = get(f"/api/bodydata/v1/device/status?mac={mac}", token)
    print("device/status :", json.dumps(status, ensure_ascii=False)[:600])
    prog = get(f"/api/bodydata/v1/firmware/upgradeProgress?mac={mac}", token)
    print("upgradeProgress:", json.dumps(prog, ensure_ascii=False)[:400])
    print()
    print("# 当前已知固件版本（来自之前在线时的 QueryDevicePropertyStatus 缓存）：")
    print("  ControllerVersion      : 18.28")
    print("  MainVersion            : 1.15")
    print("  UserInterfaceVersion   : 5.19")
    print("  ControllerConfigVersion: 0.00")
    print()
    print("# 注意：云端没有「查最新版本」的只读接口（App 里只有 POST firmware/upgrade）,")
    print("#       所以无法在不触发升级的前提下判断是否有新固件。")


def _tail(n: int) -> list[str]:
    out = subprocess.run(
        ["ssh", "-x", "-T", "-o", "BatchMode=yes", ROUTER, f"tail -n {n} {BROKER_LOG} 2>/dev/null"],
        capture_output=True, text=True, timeout=15,
    )
    return out.stdout.splitlines()


def cmd_broker_log(_args) -> None:
    lines = _tail(400)
    print(f"# broker 日志最近 {len(lines)} 行里与升级/服务相关的消息：")
    hit = 0
    for ln in lines:
        if any(k in ln for k in KEYWORDS):
            print(" ", ln[:300])
            hit += 1
    if not hit:
        print("  （没有）—— 说明没收到任何升级/服务类下发（正常，离线模式下官方不会推）")


def cmd_follow(_args) -> None:
    print("# 持续监听 broker 日志（Ctrl+C 退出）；只显示升级/服务类消息")
    proc = subprocess.Popen(
        ["ssh", "-x", "-T", "-o", "BatchMode=yes", ROUTER, f"tail -f {BROKER_LOG} 2>/dev/null"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            if any(k in line for k in KEYWORDS):
                print(time.strftime("%H:%M:%S"), line.rstrip()[:300])
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


def main() -> None:
    ap = argparse.ArgumentParser(description="按摩椅 OTA 侦察（只读）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cloud", action="store_true", help="查云端设备状态/升级进度（只读）")
    g.add_argument("--broker-log", action="store_true", help="看 broker 日志里的升级类消息")
    g.add_argument("--follow", action="store_true", help="持续监听 broker 日志")
    args = ap.parse_args()
    if args.cloud:
        cmd_cloud(args)
    elif args.broker_log:
        cmd_broker_log(args)
    else:
        cmd_follow(args)


if __name__ == "__main__":
    main()
