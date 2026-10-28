# Home Assistant 集成（已接入）

> 状态：**已安装并验证**。HA 2026.10.4（NAS 上 Docker），自定义集成 `rtchair`
> 已创建 **32 个实体**，实时轮询本地假阿里云 broker，并自带一个「按摩椅」仪表盘。

HA 地址：`http://192.168.1.50:8123`
集成位置：`/config/custom_components/rtchair`
数据来源：路由器上的假阿里云 broker `http://192.168.1.1:8891`（离线模式）

---

## 1. 已创建的实体

设备名：**荣泰按摩椅**（型号 RT7709S，固件版本自动读取）

### 开关（switch）

| entity_id | 名称 |
|---|---|
| `switch.rong_tai_an_mo_yi_dian_yuan` | 电源 |
| `switch.rong_tai_an_mo_yi_zan_ting` | 暂停 |
| `switch.rong_tai_an_mo_yi_ling_zhong_li` | 零重力 |
| `switch.rong_tai_an_mo_yi_quan_shen_qi_nang` | 全身气囊 |
| `switch.rong_tai_an_mo_yi_bi_jian_qi_nang` | 臂肩气囊 |
| `switch.rong_tai_an_mo_yi_bei_yao_qi_nang` | 背腰气囊 |
| `switch.rong_tai_an_mo_yi_tun_bu_qi_nang` | 臀部气囊 |
| `switch.rong_tai_an_mo_yi_xiao_tui_qi_nang` | 小腿气囊 |
| `switch.rong_tai_an_mo_yi_yao_yi_mo_shi_mo_ni` | 摇椅模式（模拟） |

### 下拉选择（select）

| entity_id | 名称 | 选项 |
|---|---|---|
| `select.rong_tai_an_mo_yi_zi_dong_cheng_xu` | 自动程序 | 椅上瑜伽/脑力唤醒/放松冥想/总裁尊享/女王尊享/乐龄尊享/颈肩舒缓/脊背呵护/腰臀运动/清晨活力/午间小憩/良宵甜梦 |
| `select.rong_tai_an_mo_yi_an_mo_shou_fa` | 按摩手法 | 揉捏/敲击/揉敲/叩击/指压/深度指压 |
| `select.rong_tai_an_mo_yi_an_mo_shi_chang` | 按摩时长 | 10/20/30 分钟 |
| `select.rong_tai_an_mo_yi_ji_xin_bu_wei` | 机芯部位 | 全程/局部/定点 |

### 数值（number）

| entity_id | 名称 | 范围 |
|---|---|---|
| `number.rong_tai_an_mo_yi_3d_li_du` | 3D 力度 | 0–5 |
| `number.rong_tai_an_mo_yi_ji_xin_su_du` | 机芯速度 | 1–6 |
| `number.rong_tai_an_mo_yi_qi_nang_li_du` | 气囊力度 | 0–5 |
| `number.rong_tai_an_mo_yi_bei_bu_jia_re` | 背部加热 | 0–3 |
| `number.rong_tai_an_mo_yi_xiao_tui_jia_re` | 小腿加热 | 0–3 |
| `number.rong_tai_an_mo_yi_jiao_di_gun_lun` | 脚底滚轮 | 0–3 |
| `number.rong_tai_an_mo_yi_yao_yi_hou_yang_miao_shu` | 摇椅后仰秒数 | 5–30（默认 10） |
| `number.rong_tai_an_mo_yi_yao_yi_hui_zheng_miao_shu` | 摇椅回正秒数 | 3–30（默认 5） |

### 传感器（sensor）

| entity_id | 名称 |
|---|---|
| `sensor.rong_tai_an_mo_yi_zhuang_tai` | 状态（关机/工作复位/待机/运行中） |
| `sensor.rong_tai_an_mo_yi_dang_qian_cheng_xu` | 当前程序 |
| `sensor.rong_tai_an_mo_yi_yi_yun_xing_shi_chang` | 已运行时长（秒） |
| `sensor.rong_tai_an_mo_yi_sheng_yu_shi_jian` | 剩余时间（分钟，自动按总时长-已运行算） |

### 按钮（button）

| entity_id | 名称 |
|---|---|
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_jiu_zuo_jiu_xing` | 运行程序：久坐救星（30 分钟） |
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_jian_jing_zhong_dian` | 运行程序：肩颈重点（20 分钟） |
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_shui_qian_an_shen` | 运行程序：睡前安神（20 分钟） |
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_kuai_su_hui_xue` | 运行程序：快速回血（10 分钟） |
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_yao_bu_jia_qiang` | 运行程序：腰部加强（20 分钟） |
| `button.rong_tai_an_mo_yi_yun_xing_cheng_xu_quan_shen_shu_huan` | 运行程序：全身舒缓（30 分钟） |
| `button.rong_tai_an_mo_yi_tui_bu_kong_jian_zui_da` | 腿部空间最大（小腿+膝盖伸缩到最大） |

### 新增预设程序说明

| 程序 | 时长 | 编排 |
|---|---|---|
| 快速回血 | 10 分钟 | 揉捏力度 4 → 指压 → 叩击 → 揉捏收尾，背部加热 3 档 |
| 腰部加强 | 20 分钟 | 揉敲+背腰气囊+加热 → 揉捏+全身气囊 → 敲击 → 指压 → 揉捏收尾 |
| 全身舒缓 | 30 分钟 | 揉捏轻柔+零重力+全身气囊 → 揉敲 → 敲击慢速 → 揉捏收尾 |

---

## 2. 自带仪表盘

侧边栏已经多了一个 **「按摩椅」** 页面（`http://192.168.1.50:8123/rtchair`），分 6 个区块：

1. **概览** — 状态 / 当前程序 / 时长 / 已运行 / 剩余时间（实时模板）
2. **控制** — 电源、暂停、零重力、全身气囊（Tile 开关）
3. **程序** — 自动程序下拉 + 6 个一键预设按钮
4. **手法与部位** — 手法 / 部位 / 时长 下拉
5. **力度与加热** — 6 个数值滑杆
6. **气囊分区** — 臂肩 / 背腰 / 臀部 / 小腿 开关

配置源文件：`examples/dashboard.json`（`./tools/ha_deploy.sh` 会自动装进 HA）。

## 2.5 摇椅模式（模拟，零重力版）

**RT7709S 没有原生摇椅功能**（同系列 RT7709Pro / A50Max 等才有「一键摇椅」，
RT7709S 的机型配置里没有 `RockingChairSwitch`；实测直接下发该属性，MCU 遥测无任何反应）。

用**零重力整椅后仰/回正**循环模拟摇椅，前后两程时间可以分开调：

```
打开开关时：先把小腿伸缩 + 膝盖伸缩拉到最大（约 10 秒）→ 腿部空间最大
循环：零重力开（后仰）→ 停 1 秒 → 零重力关（回正）→ 停 1 秒 → 重复
```

**关于电机速度**：靠背/腿托电机是**恒速**的，协议里没有速度参数（TSL 只有
`0 停 / 1 升 / 2 降`；零重力只有开/关两档，二档会被拒绝）。所以「更快」只能靠
**缩短每程时间、减小幅度、提高摆动频率**——现在就是这么做的，等待时间已压到 0.8 秒。

**默认参数（最快档）**

| 实体 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `switch.rong_tai_an_mo_yi_yao_yi_mo_shi_mo_ni` | 关 | — | 摇椅模式开关，打开自动开机 |
| `number.rong_tai_an_mo_yi_yao_yi_hou_yang_miao_shu` | **3 秒** | 2–30 | 后仰停留时间 |
| `number.rong_tai_an_mo_yi_yao_yi_hui_zheng_miao_shu` | **2 秒** | 1–30 | 回正停留时间（越小越快） |
| `button.rong_tai_an_mo_yi_tui_bu_kong_jian_zui_da` | — | — | 单独把腿托伸到最大（不在摇椅模式时也能用） |

默认一圈 ≈ 3 + 0.5 + 2 + 0.5 = **约 6 秒**（最快档，实测已跑过 5 轮）。
最极限：后仰 2、回正 1 → 一圈约 4 秒（基本就是轻晃）。
想更大摇幅：后仰 10–15、回正 6–10。

- 位置：仪表盘单独一个 **「摇椅模式」** 区块
- 关闭开关会立即停止循环并把零重力复位（回正）
- 实测：腿托伸缩、零重力后仰/回正动作均正常

注意：
- 打开前确认**腿托前方/椅子后方留出空间**（腿托会先伸到最大）
- 幅度和频率是跷跷板：越短越快但幅度越小；太短就会变成轻微抖动而不是摇椅
- 建议单次 10–20 分钟；中途不舒服随时关闭
- 每程秒数别设太小（后仰 ≥5 秒、回正 ≥3 秒），避免电机频繁启停

## 3. 怎么用## 3. 怎么用## 3. 怎么用

- **设备页**：HA → 设置 → 设备与服务 → 应看到「荣泰按摩椅」，点进去就是上面这些实体
- **仪表盘**：随便加个卡片，比如「实体」卡片勾选开关 + 下拉；或者用 Mushroom 卡片
- **语音**：`打开按摩椅电源`、`把按摩手法切成指压` 等（HA Assist 支持中文实体名）

### 自动化示例

```yaml
# 晚上 22:00 自动开始「睡前安神」
automation:
  - alias: 按摩椅-睡前放松
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.rong_tai_an_mo_yi_yun_xing_cheng_xu_shui_qian_an_shen
```

```yaml
# 一键肩颈（脚本）
script:
  massage_neck:
    alias: 按摩-肩颈 20 分钟
    sequence:
      - service: switch.turn_on
        target: {entity_id: switch.rong_tai_an_mo_yi_dian_yuan}
      - delay: "00:00:04"
      - service: select.select_option
        target: {entity_id: select.rong_tai_an_mo_yi_an_mo_shou_fa}
        data: {option: "指压"}
      - service: number.set_value
        target: {entity_id: number.rong_tai_an_mo_yi_3d_li_du}
        data: {value: 4}
```

```yaml
# 离开家自动关机
automation:
  - alias: 按摩椅-人走关机
    trigger:
      - platform: state
        entity_id: person.liu
        to: "not_home"
        for: "00:05:00"
    condition:
      - condition: state
        entity_id: switch.rong_tai_an_mo_yi_dian_yuan
        state: "on"
    action:
      - service: switch.turn_off
        target: {entity_id: switch.rong_tai_an_mo_yi_dian_yuan}
```

---

## 4. 维护

```bash
# 改了集成代码后，一键重新部署（上传 + 重启 HA）
./tools/ha_deploy.sh

# 看集成日志
ssh homeassistant "sudo docker logs home-assistant --tail 100 2>&1 | grep rtchair"

# 重启 HA
ssh homeassistant "sudo docker restart home-assistant"
```

本地源码在 `custom_components/rtchair/`。

## 5. 注意

1. 依赖**离线模式**：先跑 `./tools/offline_on.sh`，否则集成连不上 broker（实体显示不可用）
2. 椅子状态是模组「有变化才上报」——如果实体长时间不更新，发一条指令或开一次机即可刷新
3. HA 里原本就有的报错（`mqtt: Not authorized`、`haier`、`xiaomi_home` 重连）与本次集成无关
4. 配置条目已手工写入 `.storage/core.config_entries`（备份文件 `core.config_entries.bak-rtchair*`），
   如果想改成不同 broker 地址，可以在 HA 里删除集成重新添加，或直接改配置条目
