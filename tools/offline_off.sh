#!/usr/bin/env bash
# 关闭「离线模式」，恢复成正常连荣泰云。
#
#   ./tools/offline_off.sh
#
# 之后椅子会在 1 分钟内自动重连真云（或把椅子电源拔插一次立即生效）。

set -uo pipefail
ROUTER="${ROUTER:-ImmortalWrt}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m!!\033[0m %s\n' "$*"; exit 1; }

ssh -x -T -o BatchMode=yes -o ConnectTimeout=8 "$ROUTER" "echo ok" >/dev/null 2>&1 \
  || die "ssh $ROUTER 连不上"

say "停止 broker 服务并删除 DNAT/放行规则"
ssh -x -T -o BatchMode=yes "$ROUTER" 'sh -s' <<'REMOTE'
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
/etc/init.d/rtchair-broker stop >/dev/null 2>&1
/etc/init.d/rtchair-broker disable >/dev/null 2>&1
uci -q delete firewall.chair_mqtt
uci -q delete firewall.chair_mqtt_allow
uci commit firewall
/etc/init.d/firewall restart >/dev/null 2>&1
sleep 1
echo "  路由规则已移除"
REMOTE

say "把 CLI 切回云端模式"
( cd "$(dirname "$0")/../rtchair" 2>/dev/null && python3 rtchair.py mode cloud ) || true

echo
echo "完成。椅子会在约 1 分钟内重连荣泰云；想立即生效就拔插一次椅子电源。"
echo "官方 App 应能重新看到设备。"
