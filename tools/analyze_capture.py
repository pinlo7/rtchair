#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_capture.py —— 解析 capture_chair_cloud.sh 抓到的 pcap，
把按摩椅 Wi-Fi 模组那条 TCP 连接的上/下行字节流按 55AA 帧拆出来。

用法：
    python3 tools/analyze_capture.py /tmp/chair_cloud.pcap
    python3 tools/analyze_capture.py /tmp/chair_cloud.pcap --chair-ip 192.168.1.100

输出：
    - 按摩椅相关的 TCP 五元组
    - 每条连接的上行(椅子→云) / 下行(云→椅子) 帧列表
      * 上行是 MCU 自己发的（状态、ACK）
      * 下行就是「云端下发的控制帧」——这就是我们要的命令！
    - 无法识别成 55AA 帧的原始数据（可能是模组自己的协议，也要看）
"""

import argparse
import collections
import struct
import sys

MCU, MODULE = 0x01, 0x0E
CMD_NAMES = {
    0x0202: "配置块", 0x0204: "心跳", 0x0205: "状态遥测",
    0x0209: "事件/ACK", 0x0247: "偏好块",
}


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def read_pcap(path):
    """返回 [(ts, src_ip, sport, dst_ip, dport, tcp_payload_bytes)]"""
    raw = open(path, "rb").read()
    if len(raw) < 24:
        raise SystemExit("不是有效的 pcap")
    magic = raw[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        raise SystemExit(f"不认识的 pcap 魔数 {magic!r}（可能是 pcapng，用 tcpdump -r 转一下）")
    off = 24
    out = []
    while off + 16 <= len(raw):
        ts_sec, ts_usec, incl, _orig = struct.unpack(endian + "IIII", raw[off:off + 16])
        off += 16
        pkt = raw[off:off + incl]
        off += incl
        if len(pkt) < 14:
            continue
        eth_type = struct.unpack("!H", pkt[12:14])[0]
        l3 = 14
        while eth_type in (0x8100, 0x88A8) and len(pkt) >= l3 + 4:
            eth_type = struct.unpack("!H", pkt[l3 + 2:l3 + 4])[0]
            l3 += 4
        if eth_type != 0x0800 or len(pkt) < l3 + 20:
            continue
        ip = pkt[l3:]
        ihl = (ip[0] & 0x0F) * 4
        if ip[9] != 6:
            continue
        src_ip = ".".join(str(x) for x in ip[12:16])
        dst_ip = ".".join(str(x) for x in ip[16:20])
        total_len = struct.unpack("!H", ip[2:4])[0]
        tcp = ip[ihl:total_len]
        if len(tcp) < 20:
            continue
        sport, dport = struct.unpack("!HH", tcp[0:4])
        doff = (tcp[12] >> 4) * 4
        payload = tcp[doff:]
        out.append((ts_sec + ts_usec / 1e6, src_ip, sport, dst_ip, dport, payload))
    return out


# ---------------------------------------------------------------- MQTT (阿里云 IoT)
MQTT_NAMES = {1:"CONNECT",2:"CONNACK",3:"PUBLISH",4:"PUBACK",5:"PUBREC",6:"PUBREL",
              7:"PUBCOMP",8:"SUBSCRIBE",9:"SUBACK",10:"UNSUBSCRIBE",11:"UNSUBACK",
              12:"PINGREQ",13:"PINGRESP",14:"DISCONNECT"}


def _mqtt_len(buf, i):
    mult, val, n = 1, 0, 0
    while i + n < len(buf) and n < 4:
        b = buf[i + n]; val += (b & 0x7F) * mult; mult *= 128; n += 1
        if not (b & 0x80):
            return val, n
    return None, 0


def parse_mqtt(buf):
    """返回 [(type_name, flags, topic, payload_hex)] 与剩余未解析字节"""
    out, i = [], 0
    while i < len(buf):
        b0 = buf[i]
        typ, flags = b0 >> 4, b0 & 0x0F
        if typ == 0 or typ > 14:
            out.append(("RAW", 0, "", buf[i:].hex()))
            return out, b""
        rem, n = _mqtt_len(buf, i + 1)
        if rem is None or i + 1 + n + rem > len(buf):
            return out, buf[i:]
        body = buf[i + 1 + n: i + 1 + n + rem]
        i = i + 1 + n + rem
        name = MQTT_NAMES.get(typ, f"?{typ}")
        topic, payload = "", ""
        if typ == 3 and len(body) >= 2:            # PUBLISH
            tlen = struct.unpack("!H", body[0:2])[0]
            topic = body[2:2 + tlen].decode("utf-8", "replace")
            payload = body[2 + tlen:].hex()
        elif typ == 8 and len(body) >= 2:          # SUBSCRIBE
            tlen = struct.unpack("!H", body[2:4])[0]
            topic = body[4:4 + tlen].decode("utf-8", "replace")
        out.append((name, flags, topic, payload))
    return out, b""


def _pretty_payload(hexstr):
    try:
        b = bytes.fromhex(hexstr)
    except ValueError:
        return hexstr
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return hexstr


def split_frames(buf):
    """返回 (frames, leftover)"""
    frames, i = [], 0
    while True:
        j = buf.find(b"\x55\xaa", i)
        if j < 0 or j + 9 > len(buf):
            return frames, buf[i:]
        dst, src, seq = buf[j + 2], buf[j + 3], buf[j + 4]
        cmd = buf[j + 6] << 8 | buf[j + 5]
        ln = buf[j + 7] | (buf[j + 8] << 8)
        end = j + 9 + ln + 2
        if ln > 4096 or end > len(buf):
            return frames, buf[j:]
        payload = buf[j + 9:j + 9 + ln]
        crc_wire = buf[end - 2] | (buf[end - 1] << 8)
        frames.append({
            "dst": dst, "src": src, "seq": seq, "cmd": cmd,
            "payload": payload.hex(), "crc_ok": crc_wire == crc16(buf[j:end - 2]),
            "raw": buf[j:end].hex(),
        })
        i = end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--chair-ip", default=None)
    args = ap.parse_args()

    pkts = [p for p in read_pcap(args.pcap) if p[5]]
    if not pkts:
        raise SystemExit("pcap 里没有 TCP 载荷")

    # 找出和椅子有关的 TCP 流
    flows = collections.OrderedDict()
    for ts, sip, sp, dip, dp, pl in pkts:
        key = tuple(sorted([(sip, sp), (dip, dp)]))
        flows.setdefault(key, []).append((ts, sip, sp, dip, dp, pl))

    def is_chair_flow(key):
        if args.chair_ip:
            return any(ip == args.chair_ip for ip, _ in key)
        return True

    cand = [(k, v) for k, v in flows.items() if is_chair_flow(k)]
    cand.sort(key=lambda kv: -len(kv[1]))
    print(f"# pcap: {args.pcap}   TCP 流 {len(flows)} 条，载荷包 {len(pkts)} 个\n")

    for key, items in cand[:8]:
        ips = [f"{ip}:{p}" for ip, p in key]
        total = sum(len(x[5]) for x in items)
        print("=" * 70)
        print(f"# 流 {ips[0]} <-> {ips[1]}   包数={len(items)}  字节={total}")
        # 两个方向分别重组
        dirs = collections.defaultdict(bytearray)
        for ts, sip, sp, dip, dp, pl in items:
            dirs[(sip, sp)] += pl
        mqtt = any(dp == 1883 or sp == 1883 for _ip, dp in [key[0], key[1]])
        for (sip, sp), blob in dirs.items():
            if mqtt:
                msgs, left = parse_mqtt(bytes(blob))
                print(f"\n-- MQTT 方向 {sip}:{sp} -> 对端   {len(blob)} 字节")
                for name, flags, topic, pl in msgs:
                    if not pl:
                        print(f"   {name}" + (f"  topic={topic}" if topic else ""))
                        continue
                    if name == "PUBLISH":
                        print(f"   PUBLISH {topic}")
                        print(f"           payload = {_pretty_payload(pl)}")
                    else:
                        print(f"   {name} {pl[:80]}")
                if left:
                    print(f"   ! 剩余 {len(left)} 字节: {left[:48].hex()}")
                continue
            frames, left = split_frames(bytes(blob))
            ok = sum(1 for f in frames if f["crc_ok"])
            print(f"\n-- 方向 {sip}:{sp} -> 对端    {len(blob)} 字节，"
                  f"解析出 {len(frames)} 帧（CRC 正确 {ok}）")
            if not frames:
                print(f"   前 64 字节: {bytes(blob)[:64].hex()}")
                continue
            counts = collections.Counter(f["cmd"] for f in frames)
            print("   命令统计:", "  ".join(f"{c:04X}({CMD_NAMES.get(c,'?')})×{n}"
                                            for c, n in counts.most_common(12)))
            # 只打印「不常见」的帧——云端下发的控制帧通常只出现 1~几次
            for f in frames:
                if counts[f["cmd"]] <= 6:
                    print(f"   ★ cmd={f['cmd']:04X} dst={f['dst']:02X} src={f['src']:02X} "
                          f"seq={f['seq']:02X} crc_ok={f['crc_ok']} payload={f['payload']}")
            if left:
                print(f"   ! 剩余未成帧 {len(left)} 字节: {left[:48].hex()}")


if __name__ == "__main__":
    main()
