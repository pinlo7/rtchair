#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtchair_local —— 荣泰 RT7709S 局域网(离线)通道工具

背景：RT7709S 的 Wi-Fi 模组是 汉枫 HF-LPB130，除了连云之外还在局域网
192.168.1.100:8899 开着一个 TCP 透传口，把按摩椅主控(MCU)的串口数据
原样吐出来。也就是说：**不联网也能实时读到按摩椅的全部状态帧**。

本工具做三件事：
  1. scan      在局域网里按 MAC 找到按摩椅的 IP
  2. monitor   实时显示 MCU 上行帧（55 AA … CRC16）
  3. send      往 MCU 发一帧（实验用，见 docs/离线控制方案.md）

帧格式（已用 MCU 上行帧逐帧校验通过）：
  55 AA | dst | src | seq | cmdLo cmdHi | lenLo lenHi | payload… | crcLo crcHi
  - src/dst：MCU=0x01，Wi-Fi 模组=0x0E
  - CRC16/CCITT-FALSE(poly 0x1021, init 0xFFFF)，低字节在前
  - 上行常见 cmd：0x0202 配置块 / 0x0204 心跳 / 0x0205 状态遥测 /
                  0x0209 事件 / 0x0247 偏好块

用法：
  python3 rtchair_local.py scan
  python3 rtchair_local.py monitor
  python3 rtchair_local.py write-test --list
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time

DEFAULT_PORT = 8899
MCU_ADDR = 0x01
MODULE_ADDR = 0x0E
CHAIR_MAC = os.environ.get("RT_MAC", "")  # 例如 AA:BB:CC:DD:EE:FF；也可在 config 里配 mac

CMD_NAMES = {
    0x0202: "配置块(64B)",
    0x0204: "心跳/空帧",
    0x0205: "状态遥测(32B)",
    0x0209: "事件(空)",
    0x0247: "偏好块(32B)",
}


# --------------------------------------------------------------------------
def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_frame(dst, src, seq, cmd, payload=b""):
    b = bytes([0x55, 0xAA, dst, src, seq, cmd & 0xFF, (cmd >> 8) & 0xFF,
               len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]) + bytes(payload)
    c = crc16(b)
    return b + bytes([c & 0xFF, (c >> 8) & 0xFF])


def parse_frames(buf):
    out = []
    i = 0
    while True:
        j = buf.find(b"\x55\xaa", i)
        if j < 0 or j + 9 > len(buf):
            break
        dst, src, seq = buf[j + 2], buf[j + 3], buf[j + 4]
        cmd = buf[j + 6] << 8 | buf[j + 5]
        ln = buf[j + 7] | (buf[j + 8] << 8)
        end = j + 9 + ln + 2
        if ln > 4096 or end > len(buf):
            break
        payload = buf[j + 9:j + 9 + ln]
        crc_wire = buf[end - 2] | (buf[end - 1] << 8)
        out.append({
            "dst": dst, "src": src, "seq": seq, "cmd": cmd, "len": ln,
            "payload": payload.hex(), "crc_ok": crc_wire == crc16(buf[j:end - 2]),
        })
        i = end
    return out


# --------------------------------------------------------------------------
def load_cfg():
    p = os.path.join(os.path.expanduser("~"), ".config", "rtchair", "config.json")
    cfg = {}
    if os.path.exists(p):
        try:
            cfg = json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    mac = os.environ.get("RT_MAC") or cfg.get("mac")
    ip = os.environ.get("RT_LAN_IP") or cfg.get("lan_ip")
    if mac and len(mac) == 12 and ":" not in mac:
        mac = ":".join(mac[i:i + 2] for i in range(0, 12, 2))
    return mac.upper() if mac else None, ip


def arp_table():
    tbl = {}
    try:
        for line in open("/proc/net/arp").read().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                tbl[parts[3].upper()] = parts[0]
    except Exception:
        pass
    return tbl


def find_chair_ip(mac, subnet=None):
    mac = mac.upper()
    ip = arp_table().get(mac)
    if ip:
        return ip
    # ping 扫描一遍再查 ARP
    if subnet is None:
        out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"],
                             capture_output=True, text=True).stdout.split()
        try:
            src = out[out.index("src") + 1]
            subnet = src.rsplit(".", 1)[0]
        except Exception:
            return None
    print(f"在 {subnet}.0/24 里找 {mac} …", file=sys.stderr)
    procs = []
    for i in range(1, 255):
        procs.append(subprocess.Popen(
            ["ping", "-c", "1", "-W", "1", f"{subnet}.{i}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for p in procs:
        p.wait()
    return arp_table().get(mac)


# --------------------------------------------------------------------------
def cmd_scan(args):
    mac, ip = load_cfg()
    mac = args.mac.upper() if args.mac else mac
    if not mac:
        sys.exit("没有 MAC：先在手机 App 里配好，或 --mac AA:BB:CC:DD:EE:FF")
    ip = ip or find_chair_ip(mac)
    if not ip:
        print("没找到按摩椅。请确认椅子和电脑在同一个 Wi-Fi/局域网，且椅子通电。")
        return 1
    print(f"按摩椅 {mac}  ->  {ip}:{DEFAULT_PORT}")
    ok = probe_port(ip)
    print("8899 端口:", "开放（离线通道可用）" if ok else "不通（模组可能休眠/换了网络）")
    if ok:
        cfgp = os.path.join(os.path.expanduser("~"), ".config", "rtchair", "config.json")
        try:
            cfg = json.load(open(cfgp, encoding="utf-8")) if os.path.exists(cfgp) else {}
            cfg["lan_ip"] = ip
            os.makedirs(os.path.dirname(cfgp), exist_ok=True)
            json.dump(cfg, open(cfgp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            os.chmod(cfgp, 0o600)
            print("已记住局域网地址 ->", cfgp)
        except Exception as e:
            print("保存地址失败:", e)
    return 0


def probe_port(ip, port=DEFAULT_PORT, timeout=1.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def connect(ip=None, port=DEFAULT_PORT):
    if not ip:
        _, ip = load_cfg()
    if not ip:
        mac, _ = load_cfg()
        ip = find_chair_ip(mac) if mac else None
    if not ip:
        sys.exit("找不到按摩椅 IP，先运行：python3 rtchair_local.py scan")
    s = socket.socket()
    s.settimeout(10)
    s.connect((ip, port))
    return s, ip


def _describe(f):
    name = CMD_NAMES.get(f["cmd"], "")
    flag = "" if f["crc_ok"] else "  [CRC错!]"
    return (f"{time.strftime('%H:%M:%S')}  dst={f['dst']:02X} src={f['src']:02X} "
            f"seq={f['seq']:02X} cmd={f['cmd']:04X} len={f['len']:2d} "
            f"{name}{flag}\n            {f['payload']}")


def cmd_monitor(args):
    s, ip = connect()
    print(f"# 已连接 {ip}:{DEFAULT_PORT}，Ctrl+C 退出")
    buf = b""
    seen = {}
    t0 = time.time()
    try:
        while True:
            if args.duration and time.time() - t0 > args.duration:
                break
            try:
                d = s.recv(4096)
            except socket.timeout:
                continue
            if not d:
                print("# 连接被对端关闭")
                break
            buf += d
            frames = parse_frames(buf)
            # 只保留未解析的尾巴
            if frames:
                last_len = 9 + frames[-1]["len"] + 2
                idx = buf.rfind(b"\x55\xaa")
                # 简单处理：裁掉已消费部分
                pos = 0
                for f in frames:
                    pos += 9 + f["len"] + 2
                buf = buf[pos:]
            for f in frames:
                seen[f["cmd"]] = seen.get(f["cmd"], 0) + 1
                print(_describe(f))
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        print("\n# 统计:", "  ".join(f"{c:04X}×{n}" for c, n in sorted(seen.items())))


def cmd_snapshot(args):
    s, ip = connect()
    buf = b""
    t0 = time.time()
    s.settimeout(1)
    while time.time() - t0 < args.seconds:
        try:
            d = s.recv(4096)
            if not d:
                break
            buf += d
        except socket.timeout:
            pass
    s.close()
    frames = parse_frames(buf)
    out = {"ip": ip, "frames": frames}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for f in frames:
            print(_describe(f))
        print(f"\n# 共 {len(frames)} 帧，CRC 全部正确: {all(f['crc_ok'] for f in frames)}")


def cmd_send(args):
    """发一帧到 MCU；默认 dst=0x01 src=0x0E。--payload 十六进制。"""
    payload = bytes.fromhex(args.payload.replace(" ", "")) if args.payload else b""
    if args.frame:
        frame = bytes.fromhex(args.frame.replace(" ", ""))
    else:
        frame = build_frame(args.dst, args.src, args.seq, args.cmd, payload)
    s, ip = connect()
    s.settimeout(2)
    print(f"# -> {frame.hex()}")
    s.sendall(frame)
    time.sleep(args.wait)
    buf = b""
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
            buf += d
    except socket.timeout:
        pass
    s.close()
    for f in parse_frames(buf):
        if f["cmd"] == args.cmd or f["dst"] != MODULE_ADDR:
            print("<-", _describe(f).split("\n")[0])


WRITE_TESTS = [
    ("开机 directive 0x0001 -> payload 0100", 0x2001, "0100"),
    ("开机 directive 0x0001 -> payload 0001", 0x2001, "0001"),
    ("关机 directive 0x0000 -> payload 0000", 0x2001, "0000"),
    ("标准协议 SettingMassageSkill=指压 0x2005", 0x2001, "0520"),
    ("RT7709S 指压 directive 0x2012", 0x2001, "1220"),
    ("程序 椅上瑜伽 directive 0x1020", 0x2001, "2010"),
    ("程序 椅上瑜伽 作为帧命令", 0x1020, ""),
]


def cmd_write_test(args):
    if args.list:
        for i, (name, cmd, pl) in enumerate(WRITE_TESTS):
            print(f"{i}: {name}   cmd=0x{cmd:04X} payload={pl}")
        return
    name, cmd, pl = WRITE_TESTS[args.index]
    payload = bytes.fromhex(pl)
    frame = build_frame(MCU_ADDR, MODULE_ADDR, 0xE0 + args.index, cmd, payload)
    s, ip = connect()
    s.settimeout(1.5)
    print(f"# {name}\n# -> {frame.hex()}")
    s.sendall(frame)
    time.sleep(1.5)
    buf = b""
    try:
        while True:
            buf += s.recv(4096)
    except socket.timeout:
        pass
    s.close()
    acked = [f for f in parse_frames(buf) if f["cmd"] == cmd and f["dst"] != MODULE_ADDR]
    print("# MCU 应答:", acked[0] if acked else "无")
    print("# 注意：MCU 只做传输层 ACK；这条命令是否生效要看椅子有没有动作")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="荣泰 RT7709S 局域网离线通道工具")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("scan", help="按 MAC 找到按摩椅局域网 IP")
    p.add_argument("--mac", help="默认读配置")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("monitor", help="实时显示 MCU 上行帧")
    p.add_argument("-d", "--duration", type=float, default=0, help="秒，0=一直")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("snapshot", help="抓一段帧输出 JSON")
    p.add_argument("-s", "--seconds", type=float, default=5)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("send", help="发一帧（实验）")
    p.add_argument("--cmd", type=lambda x: int(x, 0), required=True)
    p.add_argument("--payload", default="", help="十六进制，如 0001")
    p.add_argument("--dst", type=lambda x: int(x, 0), default=MCU_ADDR)
    p.add_argument("--src", type=lambda x: int(x, 0), default=MODULE_ADDR)
    p.add_argument("--seq", type=lambda x: int(x, 0), default=0x01)
    p.add_argument("--wait", type=float, default=1.5)
    p.add_argument("--frame", help="直接给整帧十六进制")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("write-test", help="跑一组已知候选命令（观察椅子反应）")
    p.add_argument("--list", action="store_true")
    p.add_argument("--index", type=int, default=0)
    p.set_defaults(func=cmd_write_test)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
