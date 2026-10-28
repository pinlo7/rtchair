#!/usr/bin/env bash
# 把 HA 自定义集成 rtchair 部署到 NAS 上的 Home Assistant（Docker）并重启
#   ./tools/ha_deploy.sh
# 依赖：homeassistant 的免密 ssh（~/.ssh/config 里 Host homeassistant）
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/ha/custom_components/rtchair"
REMOTE_HOST="${HA_HOST:-homeassistant}"
HA_CFG_DIR="${HA_CFG_DIR:-/config}"
CONTAINER="${HA_CONTAINER:-home-assistant}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m!!\033[0m %s\n' "$*"; exit 1; }

[[ -d "$SRC" ]] || die "找不到 $SRC"
ssh -x -T -o BatchMode=yes "$REMOTE_HOST" "echo ok" >/dev/null 2>&1 || die "ssh $REMOTE_HOST 连不上"

say "上传 custom_components/rtchair"
tar -C "$(dirname "$SRC")" -cf - rtchair | \
  ssh -x -T -o BatchMode=yes "$REMOTE_HOST" \
  "sudo mkdir -p $HA_CFG_DIR/custom_components && sudo tar -C $HA_CFG_DIR/custom_components -xf - && sudo chown -R root:root $HA_CFG_DIR/custom_components/rtchair && echo ok" \
  || die "上传失败"

DASH="$REPO/examples/dashboard.json"
if [[ -f "$DASH" ]]; then
  say "上传按摩椅仪表盘"
  scp -q "$DASH" "$REMOTE_HOST:/tmp/rtchair_dashboard.json" || die "上传仪表盘失败"
fi

say "停止 Home Assistant 容器（写入 storage 时不能运行）"
ssh -x -T -o BatchMode=yes "$REMOTE_HOST" "sudo docker stop $CONTAINER >/dev/null 2>&1; echo stopped"

if [[ -f "$DASH" ]]; then
  say "写入 Lovelace 仪表盘 + 侧边栏注册"
  ssh -x -T -o BatchMode=yes "$REMOTE_HOST" "export PATH=\$PATH:/usr/sbin:/sbin; sudo python3 - <<'PY'
import json, shutil, time, os
S='$HA_CFG_DIR/.storage'
cfg=json.load(open('/tmp/rtchair_dashboard.json'))
ts=time.strftime('%Y%m%d%H%M%S')
p=S+'/lovelace.rtchair'
if os.path.exists(p): shutil.copy2(p, p+'.bak-'+ts)
json.dump({'version':1,'minor_version':1,'key':'lovelace.rtchair','data':{'config':cfg}}, open(p,'w'), ensure_ascii=False, indent=2)
p2=S+'/lovelace_dashboards'
shutil.copy2(p2, p2+'.bak-'+ts)
d=json.load(open(p2)); items=d['data']['items']
if not any(i.get('url_path')=='rtchair' for i in items):
    items.append({'id':'rtchair','icon':'mdi:chair-rolling','title':'按摩椅','url_path':'rtchair','mode':'storage','require_admin':False,'show_in_sidebar':True})
    json.dump(d, open(p2,'w'), ensure_ascii=False, indent=2)
print('dashboard written')
PY" || die "写入仪表盘失败"
fi

say "启动 Home Assistant 容器"
ssh -x -T -o BatchMode=yes "$REMOTE_HOST" "sudo docker start $CONTAINER" >/dev/null || die "启动失败"

say "完成。等待 HA 启动后，在「设置 → 设备与服务」里应能看到「荣泰按摩椅」。"
echo "  查看日志: ssh $REMOTE_HOST \"sudo docker logs $CONTAINER --tail 50 2>&1 | grep rtchair\""
