#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local_cloud_broker.py —— 在本机假装成「阿里云 IoT」，让按摩椅连过来，实现纯局域网控制。

原理（来自真实抓包）：
  椅子（HF-LPB130 模组）连阿里云 IoT 的 MQTT 1883，云端下发控制指令的方式就是：

    topic:   /sys/<productKey>/<deviceName>/thing/service/property/set
    payload: {"method":"thing.service.property.set","id":"<数字>",
              "params":{"ChairSwitch":1}, "version":"1.0.0"}

  所以只要把椅子的 1883 流量劫持到本机（路由器上一条 DNAT 规则），
  自己回 CONNACK、SUBACK，再往这个 topic 发同样的 JSON，椅子就会执行。
  全程不需要互联网、不需要荣泰云。

用法：
    python3 tools/local_cloud_broker.py                 # 监听 0.0.0.0:1883
    curl -X POST localhost:8891/set -d '{"ChairSwitch":1}'
    curl localhost:8891/status

路由重定向（在路由器上，需 root）：
    iptables -t nat -I PREROUTING -s <椅子IP> -p tcp --dport 1883 \\
        -j DNAT --to-destination <本机IP>:1883

恢复：删掉上面那条规则，椅子会自动回连真云。
"""

import json
import socket
import struct
import sys
import threading
import time

LOG_PATH = "/tmp/local_cloud_broker.log"
STATE_PATH = "/root/rtchair_props.json"
_lock = threading.Lock()
_state = {
    "connected": False,
    "client_id": "",
    "product_key": "",
    "device_name": "",
    "topics": [],
    "last_rx": [],
    "props": {},
    "sent": 0,
}
_conn = {"sock": None}
try:
    _saved = json.load(open(STATE_PATH, encoding="utf-8"))
    if isinstance(_saved, dict):
        _state["props"] = _saved
except Exception:
    pass
AUTO_TEST = {"enabled": False, "done": False}
PROP_SET_TPL = "/sys/{pk}/{dn}/thing/service/property/set"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with _lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ------------------------------------------------------------------ MQTT 基础
def enc_len(n):
    out = b""
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out += bytes([b])
        if n == 0:
            return out


def dec_len(buf, i):
    mult, val, n = 1, 0, 0
    while True:
        if i + n >= len(buf):
            return None, 0
        b = buf[i + n]
        val += (b & 0x7F) * mult
        mult *= 128
        n += 1
        if not b & 0x80:
            return val, n
        if n > 4:
            return None, 0


def parse_connect(body):
    """返回 clientId / username"""
    plen = struct.unpack("!H", body[0:2])[0]
    proto = body[2:2 + plen]
    idx = 2 + plen
    ver = body[idx]
    flags = body[idx + 1]
    idx += 2
    keepalive = struct.unpack("!H", body[idx:idx + 2])[0]
    idx += 2

    def read_str(j):
        ln = struct.unpack("!H", body[j:j + 2])[0]
        return body[j + 2:j + 2 + ln].decode("utf-8", "replace"), j + 2 + ln

    cid, idx = read_str(idx)
    username = ""
    if flags & 0x80:  # username
        username, idx = read_str(idx)
    return {"proto": proto.decode("latin1"), "ver": ver, "flags": flags,
            "keepalive": keepalive, "client_id": cid, "username": username}


def build_publish(topic, payload, qos=0, pid=None):
    tb = topic.encode()
    body = struct.pack("!H", len(tb)) + tb
    if qos > 0:
        body += struct.pack("!H", pid or 1)
    body += payload.encode() if isinstance(payload, str) else payload
    hdr = 0x30 | (qos << 1)
    return bytes([hdr]) + enc_len(len(body)) + body


def build_ack(typ, pid):
    return bytes([typ << 4, 0x02]) + struct.pack("!H", pid)


# ------------------------------------------------------------------ broker
def handle_client(sock, addr):
    log(f"连接来自 {addr}")
    buf = b""
    sock.settimeout(120)
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            buf += data
            while True:
                if len(buf) < 2:
                    break
                typ = buf[0] >> 4
                flags = buf[0] & 0x0F
                rem, n = dec_len(buf, 1)
                if rem is None or len(buf) < 1 + n + rem:
                    break
                body = buf[1 + n:1 + n + rem]
                buf = buf[1 + n + rem:]

                if typ == 1:  # CONNECT
                    info = parse_connect(body)
                    cid = info["client_id"]
                    # 阿里云 username 格式: <deviceName>&<productKey>（deviceName 不一定是 clientId 前缀）
                    dn, pk = "", ""
                    if "&" in (info["username"] or ""):
                        dn, pk = info["username"].split("&", 1)
                    if not dn:
                        dn = cid.split("|")[0] if cid else ""
                    with _lock:
                        _state.update(connected=True, client_id=cid,
                                      device_name=dn, product_key=pk,
                                      topics=[])
                        _conn["sock"] = sock
                    log(f"CONNECT clientId={cid!r} username={info['username']!r} "
                        f"-> pk={pk!r} dn={dn!r}")
                    sock.sendall(b"\x20\x02\x00\x00")  # CONNACK OK
                    threading.Thread(target=_refresh_state, daemon=True).start()
                    if AUTO_TEST["enabled"] and not AUTO_TEST["done"]:
                        AUTO_TEST["done"] = True
                        threading.Thread(target=_auto_test, daemon=True).start()
                elif typ == 8:  # SUBSCRIBE
                    pid = struct.unpack("!H", body[0:2])[0]
                    j = 2
                    topics = []
                    qoss = []
                    while j < len(body):
                        tl = struct.unpack("!H", body[j:j + 2])[0]
                        t = body[j + 2:j + 2 + tl].decode("utf-8", "replace")
                        qos = body[j + 2 + tl]
                        topics.append(t)
                        qoss.append(min(qos, 1))
                        j += 2 + tl + 1
                    with _lock:
                        _state["topics"].extend(topics)
                    log(f"SUBSCRIBE {topics}")
                    ack = bytes([0x90]) + enc_len(2 + len(qoss)) + struct.pack("!H", pid) + bytes(qoss)
                    sock.sendall(ack)
                elif typ == 3:  # PUBLISH
                    qos = (flags >> 1) & 3
                    tl = struct.unpack("!H", body[0:2])[0]
                    topic = body[2:2 + tl].decode("utf-8", "replace")
                    j = 2 + tl
                    pid = None
                    if qos > 0:
                        pid = struct.unpack("!H", body[j:j + 2])[0]
                        j += 2
                    payload = body[j:].decode("utf-8", "replace")
                    short = payload.replace("\n", "").replace("\t", "")[:300]
                    with _lock:
                        _state["last_rx"].append({"t": time.time(), "topic": topic, "payload": payload})
                        _state["last_rx"] = _state["last_rx"][-20:]
                        if topic.endswith("thing/event/property/post"):
                            try:
                                msg = json.loads(payload)
                                params = msg.get("params") or {}
                                if isinstance(params, dict):
                                    _state["props"].update(params)
                                    try:
                                        with open(STATE_PATH, "w", encoding="utf-8") as f:
                                            json.dump(_state["props"], f, ensure_ascii=False)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    log(f"PUBLISH(qos{qos}) {topic}  {short}")
                    if qos == 1 and pid is not None:
                        sock.sendall(build_ack(4, pid))
                elif typ == 12:  # PINGREQ
                    sock.sendall(b"\xd0\x00")
                elif typ == 14:  # DISCONNECT
                    log("DISCONNECT")
                    return
                else:
                    log(f"未处理的 MQTT 类型 {typ} len={rem}")
    except Exception as e:
        log(f"连接异常: {e}")
    finally:
        with _lock:
            _state["connected"] = False
            _conn["sock"] = None
        try:
            sock.close()
        except Exception:
            pass
        log(f"断开 {addr}")


def _refresh_state():
    """连上后把上次已知状态回放一次，触发模组上报完整属性（值不变，不会真的动作）"""
    time.sleep(3)
    with _lock:
        props = dict(_state["props"])
    if not props:
        return
    safe = {k: v for k, v in props.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            and k.startswith(("Chair", "Setting", "Program", "Should"))}
    # 只回放「状态类」字段，避免误触发动作：电源/程序/暂停不动
    for k in ("ChairSwitch", "ProgramAuto", "ChairPause", "ResetEnd"):
        safe.pop(k, None)
    if safe:
        try:
            send_property_set(safe)
            log(f"[状态回放] 已请求刷新 {len(safe)} 个属性")
        except Exception as e:
            log(f"[状态回放] 失败: {e}")


def _auto_test():
    time.sleep(5)
    steps = [("开机", {"ChairSwitch": 1}),
             ("程序16", {"ProgramAuto": 16}),
             ("手法指压+力度3", {"SettingMassageSkill": 5, "SettingStrength3D": 3}),
             ("背部加热2", {"SettingHeatBack": 2}),
             ("时长20", {"SettingMassageTime": 2})]
    for name, params in steps:
        ok, info = send_property_set(params)
        log(f"[自测] {name} -> {ok} {info}")
        time.sleep(4)
    log("[自测] 完成")


# ------------------------------------------------------------------ 发送
def send_property_set(params):
    with _lock:
        sock = _conn["sock"]
        pk = _state["product_key"] or "<PRODUCT_KEY>"
        dn = _state["device_name"] or "<DEVICE_NAME>"
        if not sock:
            return False, "设备未连接"
        topic = PROP_SET_TPL.format(pk=pk, dn=dn)
        payload = json.dumps({
            "method": "thing.service.property.set",
            "id": str(int(time.time() * 1000) % 100000000),
            "params": params,
            "version": "1.0.0",
        }, ensure_ascii=False, separators=(",", ":"))
        sock.sendall(build_publish(topic, payload, qos=0))
        _state["sent"] += 1
    log(f"发送 -> {topic} {payload}")
    return True, topic


# ------------------------------------------------------------------ HTTP 控制
def _http_conn(conn):
    try:
        conn.settimeout(10)
        data = b""
        while b"\r\n\r\n" not in data:
            d = conn.recv(4096)
            if not d:
                return
            data += d
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode("latin1").split("\r\n")
        method, path = lines[0].split(" ")[0], lines[0].split(" ")[1]
        clen = 0
        for ln in lines[1:]:
            if ln.lower().startswith("content-length:"):
                clen = int(ln.split(":", 1)[1].strip())
        body = rest
        while len(body) < clen:
            d = conn.recv(4096)
            if not d:
                break
            body += d
        body = body[:clen]

        def reply(obj, code=200):
            raw = json.dumps(obj, ensure_ascii=False).encode()
            conn.sendall(b"HTTP/1.0 %d OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                         b"Content-Length: %d\r\nConnection: close\r\n\r\n" % (code, len(raw)) + raw)

        if method == "GET":
            with _lock:
                st = dict(_state)
            st["last_rx"] = st["last_rx"][-5:]
            reply(st)
        elif method == "POST" and path.startswith("/set"):
            try:
                params = json.loads(body or b"{}")
            except Exception:
                return reply({"error": "bad json"}, 400)
            ok, info = send_property_set(params)
            reply({"ok": ok, "info": info} if ok else {"error": info})
        else:
            reply({"error": "not found"}, 404)
    except Exception as e:
        log(f"http 异常: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def http_server(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(8)
    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_http_conn, args=(conn,), daemon=True).start()
        except Exception:
            time.sleep(0.2)


def main():
    port, http_port = 1883, 8891
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif args[i] == "--auto-test":
            AUTO_TEST["enabled"] = True; i += 1
        elif args[i] == "--http-port" and i + 1 < len(args):
            http_port = int(args[i + 1]); i += 2
        else:
            i += 1

    open(LOG_PATH, "w").close()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    log(f"MQTT broker 监听 0.0.0.0:{port}")
    log(f"控制接口: http://127.0.0.1:{http_port}/set  (POST JSON)")
    log("等待按摩椅连接…")

    threading.Thread(target=http_server, args=(http_port,), daemon=True).start()

    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
