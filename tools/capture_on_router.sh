#!/usr/bin/env bash
# 在【网关路由器】上抓「椅子 <-> 荣泰云」的 MQTT 明文，然后把 pcap 传回电脑。
#
# 为什么在路由器上抓：椅子的流量本来就全部经过网关，路由器上能同时看到
# 「椅子→云」和「云→椅子」，不用 ARP 欺骗、不影响联网。
#
# 用法（在电脑上跑；会让你输入一次路由器 SSH 密码）：
#   ./tools/capture_on_router.sh
#   ROUTER_HOST=192.168.1.1 ROUTER_USER=root ./tools/capture_on_router.sh
#
# 产物：/tmp/chair_router.pcap    日志：/tmp/capture_router.log
# 分析：python3 tools/analyze_capture.py /tmp/chair_router.pcap
#
# 说明：脚本一边在路由器上抓包，一边反复触发云端指令（椅子会动，正常），
#       这样不管 SSH 登录/capture 启动快慢，都能覆盖到控制消息。

set -uo pipefail

ROUTER_HOST="${ROUTER_HOST:-192.168.1.1}"
ROUTER_USER="${ROUTER_USER:-root}"
CHAIR_IP="${CHAIR_IP:-192.168.1.100}"
CAP_SECONDS="${CAP_SECONDS:-60}"
OUT="/tmp/chair_router.pcap"
LOG="/tmp/capture_router.log"
CFG="$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)/.config/rtchair/config.json"
SSHOPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

: > "$LOG"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
command -v ssh >/dev/null || { echo "缺 ssh"; exit 1; }
[[ -f "$CFG" ]] || { echo "找不到 $CFG，先跑 rtchair.py setup"; exit 1; }

TOKEN=$(python3 -c "import json;print(json.load(open('$CFG'))['token'])" 2>/dev/null)
MAC=$(python3 -c "import json;print(json.load(open('$CFG'))['mac'])" 2>/dev/null)
[[ -z "${TOKEN:-}" ]] && { echo "配置里没有 token"; exit 1; }

log "路由器: $ROUTER_USER@$ROUTER_HOST   椅子: $CHAIR_IP   抓 ${CAP_SECONDS}s"
log "下面请输入一次路由器 SSH 密码（输入时不显示）"

# ---------- 后台：反复触发云端指令 ----------
(
  trig() {
    curl -sS -m 10 -X POST "https://iot3.xingzhuo.xyz/api/bodydata/v1/iot" \
      -H "token: $TOKEN" -H "Content-Type: application/json" -d "$1" >/dev/null 2>&1
    echo "[$(date +%H:%M:%S)] trigger: $2" >> "$LOG"
  }
  sleep 10
  for round in 1 2 3 4 5 6 7 8; do
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"ChairSwitch\":1}}}" "开机"
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"ProgramAuto\":16}}}" "程序16"
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"SettingMassageSkill\":5,\"SettingStrength3D\":3}}}" "手法5力度3"
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"SettingHeatBack\":2}}}" "背部加热2"
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"SettingZeroGravity\":1}}}" "零重力"
    trig "{\"mac\":\"$MAC\",\"action\":\"SetDeviceProperty\",\"params\":{\"Items\":{\"SettingMassageTime\":2}}}" "时长20"
    sleep 2
  done
) & TRIG_PID=$!

# ---------- 前台：SSH 到路由器抓包并回传（base64 走 stdout） ----------
REMOTE='
set -u
CHAIR_IP="'"$CHAIR_IP"'"
SECS="'"$CAP_SECONDS"'"
CAP=/tmp/chair_cap.pcap
rm -f "$CAP"
IF=$(ip route 2>/dev/null | awk "/^default/ {print \$5; exit}")
[ -z "${IF:-}" ] && IF=br-lan
if ! command -v tcpdump >/dev/null 2>&1; then
  (opkg update >/dev/null 2>&1; opkg install tcpdump >/dev/null 2>&1) || true
fi
command -v tcpdump >/dev/null 2>&1 || { echo "ERROR_NO_TCPDUMP"; exit 3; }
echo "IFACE=$IF"
tcpdump -i "$IF" -n -s0 -U -w "$CAP" "host $CHAIR_IP and tcp port 1883" >/dev/null 2>&1 &
TP=$!
sleep 2
echo "CAPTURE_STARTED"
sleep "$SECS"
kill "$TP" 2>/dev/null
sleep 1
echo "CAPTURE_END"
echo "SIZE=$(wc -c < "$CAP" 2>/dev/null)"
echo "BEGIN_B64"
base64 "$CAP" 2>/dev/null || gbase64 "$CAP"
echo "END_B64"
'

ssh -T $SSHOPTS "$ROUTER_USER@$ROUTER_HOST" "$REMOTE" > /tmp/ssh_out.raw 2>>"$LOG"
SSH_RC=$?
kill $TRIG_PID 2>/dev/null
wait $TRIG_PID 2>/dev/null
log "SSH 退出码 $SSH_RC"

if grep -q "ERROR_NO_TCPDUMP" /tmp/ssh_out.raw 2>/dev/null; then
  log "路由器上没有 tcpdump 且 opkg 装不上。请手动在路由器执行：opkg update && opkg install tcpdump"
  exit 2
fi
if ! grep -q "BEGIN_B64" /tmp/ssh_out.raw 2>/dev/null; then
  log "没拿到 pcap，SSH 输出前 20 行："
  head -20 /tmp/ssh_out.raw
  exit 3
fi

python3 - <<'PY'
import base64, re
raw = open('/tmp/ssh_out.raw','rb').read()
m = re.search(rb'BEGIN_B64\r?\n(.*?)\r?\nEND_B64', raw, re.S)
if not m:
    raise SystemExit("没找到 base64 段")
data = base64.b64decode(m.group(1))
open('/tmp/chair_router.pcap','wb').write(data)
print(f"pcap 已保存: /tmp/chair_router.pcap  ({len(data)} 字节)")
PY
grep -E "IFACE=|SIZE=" /tmp/ssh_out.raw | head -2
ls -la "$OUT" 2>/dev/null
log "下一步：python3 tools/analyze_capture.py $OUT"
