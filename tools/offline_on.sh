#!/usr/bin/env bash
# 开启「离线模式」：让按摩椅连到路由器上的本地假阿里云，不再依赖外网/荣泰云。
#
#   ./tools/offline_on.sh
#   ./tools/offline_off.sh    # 恢复云端模式
#
# 原理：
#   - 路由器 (ImmortalWrt) 上跑一个极简 MQTT broker，冒充阿里云 IoT
#   - uci/firewall 里加一条 DNAT：椅子 → 任意IP:1883 全部转到路由器本地 broker
#   - 椅子以为自己连上了云，其实所有指令都在你家局域网内完成
#
# 前置：路由器已配置免密 SSH（本机 `ssh ImmortalWrt` 能直接登录）

set -uo pipefail
# 改成你的路由器 SSH 别名（~/.ssh/config 里的 Host）
ROUTER="${ROUTER:-router}"
DIR="$(cd "$(dirname "$0")" && pwd)"
BROKER="$DIR/local_cloud_broker.py"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m!!\033[0m %s\n' "$*"; exit 1; }

command -v ssh >/dev/null || die "缺 ssh"
[[ -f "$BROKER" ]] || die "找不到 $BROKER"

say "检查路由器 SSH：ssh $ROUTER"
ssh -x -T -o BatchMode=yes -o ConnectTimeout=8 "$ROUTER" "echo ok" >/dev/null 2>&1 \
  || die "ssh $ROUTER 连不上（先在 ~/.ssh/config 里配好免密登录）"

say "上传 broker 到路由器 /root（持久化）"
scp -q "$BROKER" "$ROUTER:/root/local_cloud_broker.py" || die "scp 失败"

say "探测路由器 LAN IP"
ROUTER_IP="${ROUTER_IP:-$(ssh -x -T -o BatchMode=yes "$ROUTER" "uci get network.lan.ipaddr 2>/dev/null" 2>/dev/null | tr -d '\r')}"
[[ -n "$ROUTER_IP" ]] || die "拿不到路由器 LAN IP，请用 ROUTER_IP=192.168.1.1 指定"
echo "  路由器 IP: $ROUTER_IP"
CTRL="http://$ROUTER_IP:8891"

# 椅子 IP：可选（不填则对所有 LAN 设备的 1883 生效）
CHAIR_IP="${CHAIR_IP:-}"

say "安装/启动 procd 服务 + 写入持久化 DNAT 规则"
ssh -x -T -o BatchMode=yes "$ROUTER" "CHAIR_IP='$CHAIR_IP' ROUTER_IP='$ROUTER_IP' sh -s" <<'REMOTE'
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

# 1) init 脚本（不存在才写）
if [ ! -f /etc/init.d/rtchair-broker ]; then
cat > /etc/init.d/rtchair-broker <<'EOF'
#!/bin/sh /etc/rc.common
START=99
STOP=10
USE_PROCD=1

start_service() {
	procd_open_instance
	procd_set_param command /usr/bin/python3 /root/local_cloud_broker.py --port 1883 --http-port 8891
	procd_set_param respawn 3600 5 0
	procd_set_param stdout 1
	procd_set_param stderr 1
	procd_close_instance
}
EOF
chmod +x /etc/init.d/rtchair-broker
fi

# 2) 持久化 DNAT + 放行（幂等）
uci -q delete firewall.chair_mqtt 2>/dev/null
uci set firewall.chair_mqtt=redirect
uci set firewall.chair_mqtt.name='chair-mqtt-to-local-broker'
uci set firewall.chair_mqtt.src='lan'
[ -n "$CHAIR_IP" ] && uci set firewall.chair_mqtt.src_ip="$CHAIR_IP"
uci set firewall.chair_mqtt.src_dport='1883'
uci set firewall.chair_mqtt.proto='tcp'
uci set firewall.chair_mqtt.dest_ip="$ROUTER_IP"
uci set firewall.chair_mqtt.dest_port='1883'
uci set firewall.chair_mqtt.target='DNAT'

uci -q delete firewall.chair_mqtt_allow 2>/dev/null
uci set firewall.chair_mqtt_allow=rule
uci set firewall.chair_mqtt_allow.name='allow-lan-to-local-broker-1883'
uci set firewall.chair_mqtt_allow.src='lan'
uci set firewall.chair_mqtt_allow.proto='tcp'
uci set firewall.chair_mqtt_allow.dest_port='1883'
uci set firewall.chair_mqtt_allow.target='ACCEPT'

uci commit firewall
/etc/init.d/firewall restart >/dev/null 2>&1
sleep 1

# 3) 启动 broker 服务（开机自启已 enable）
/etc/init.d/rtchair-broker enable >/dev/null 2>&1
/etc/init.d/rtchair-broker restart >/dev/null 2>&1
sleep 2
/etc/init.d/rtchair-broker status 2>&1 | head -1
REMOTE

say "自检：本地 broker 控制接口"
for i in 1 2 3 4 5; do
  if curl -sS -m 3 "$CTRL/status" >/tmp/offline_status.json 2>/dev/null; then break; fi
  sleep 1
done
python3 - <<'PY' || die "broker 控制接口连不上"
import json
d = json.load(open('/tmp/offline_status.json'))
print("  broker 运行中, 椅子已连接:", d.get("connected"))
PY

say "完成。现在把 CLI 切到离线模式："
echo "    cd cli && python3 rtchair.py mode local"
echo "    python3 rtchair.py status          # 读状态"
echo "    python3 rtchair.py run programs/久坐救星.plan"
echo
echo "提示：椅子此刻起连的是本地假云，官方 App 会显示离线（正常）。"
echo "      如椅子尚未连上 broker，等 1 分钟或把椅子电源拔插一次。"
