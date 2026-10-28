# rtchair —— 荣泰 RT7709S 自定义按摩程序控制台

官方 App 只能让你在 **12 个固定自动程序**里挑一个，或者调几个参数，不能把「手法 + 力度 +
速度 + 部位 + 加热 + 气囊」按时间拼成自己的程序。这个工具补上这一块：

- 直接调用荣泰 IoT 云（App 自己用的那条接口），把任意属性组合按 **秒级时间线**下发
- 电脑上跑 CLI，或启动一个手机浏览器能开的控制面板
- 完全不影响官方 App，不刷机、不改固件

## 0. 前置条件

- Python 3.8+（只用标准库，无需 pip install）
- 按摩椅在 Wi-Fi 上且云端在线（官方 App 能连上就满足）
- 只有首次提取 token 需要电脑装好 `adb`（Android SDK platform-tools）

## 1. 首次配置（提取 token / 按摩椅 MAC）

```bash
python3 rtchair.py setup
```

手机解锁好，弹出「完全备份」对话框时点 **备份我的数据**（不要输入密码）。
脚本会从备份里读出登录 token 和按摩椅 MAC，写入 `~/.config/rtchair/config.json`，
并做一次云端连通性自检。

> 这个备份只在你自己的电脑上解析，token 等同账号凭据，配置文件权限已设为 600，请勿外传。

## 2. 常用命令

```bash
python3 rtchair.py status                 # 看当前状态
python3 rtchair.py on                     # 开机
python3 rtchair.py off                    # 关机
python3 rtchair.py auto 椅上瑜伽           # 跑官方自动程序（也接受编号 16~27）
python3 rtchair.py set 手法=指压 力度=4 部位=局部 背热=2
python3 rtchair.py run programs/久坐救星.plan        # 跑自定义时间线
python3 rtchair.py run programs/久坐救星.plan --dry-run   # 只打印不执行
python3 rtchair.py serve                  # 手机控制面板 http://<电脑IP>:8770
python3 rtchair.py props                  # 列出所有属性和取值
```

## 3. 写自己的程序（.plan 文件）

一个 `.plan` 是纯文本，每行「时间 指令」，时间是 `分:秒`：

```
# 名称: 我的程序
# 说明: 一句话描述
00:00  开机
00:05  时长=30 手法=揉捏 力度=3 速度=2 部位=全程 背热=2
06:00  手法=指压 部位=局部 力度=4
12:00  气囊=全身 气囊力度=4 零重力=开
24:00  手法=敲击 速度=1 力度=2
29:20  关机
```

可用指令：

| 写法 | 说明 |
|---|---|
| `开机` / `关机` | 电源（等价于 `电源=开/关`） |
| `暂停` / `继续` | 暂停/恢复 |
| `时长=10/20/30` | 按摩总时长（椅子只支持这三档） |
| `手法=揉捏/敲击/揉敲/叩击/指压/深度指压` | 按摩手法 |
| `力度=0~5` | 3D 力度 |
| `速度=1~6` | 机芯速度 |
| `部位=全程/局部/定点` | 机芯按摩区域 |
| `背热=0~3` / `腿热=0~3` | 背部 / 小腿加热档位 |
| `气囊=全身/臂肩/背腰/臀部/腿脚/关` | 打开对应部位气囊 |
| `气囊力度=0~5` | 气囊充气力度 |
| `零重力=开/关` | 零重力姿态 |
| `滚轮=0~3` | 脚底滚轮 |
| `靠背=升/降/停止`、`腿升降=`、`小腿伸缩=`、`膝盖伸缩=` | 姿态微调 |

也支持空格写法（`手法 指压`）和英文键名（`skill`、`strength`、`speed`、`position`、
`heat_back`、`airbag`…），完整列表见 `python3 rtchair.py props`。

> 建议在 30 分钟上限内编排；`run` 只负责按时间下发，不会在你按 Ctrl+C 后自动关机
> （按摩椅保持当前状态，需要时再 `off`）。

## 4. 手机控制面板

```bash
python3 rtchair.py serve
# 电脑会打印 http://192.168.x.x:8770
# 手机连同一个 Wi-Fi，用浏览器打开即可：
#  - 看实时状态、开关机、暂停
#  - 一键跑官方 12 个自动程序
#  - 一键跑 programs/ 里的自定义程序
#  - 直接在手机上编辑时间线并运行
```

## 5. 常见问题

**`未配置 token / mac`**
→ 先跑 `python3 rtchair.py setup`；或手动 `export RT_TOKEN=... RT_MAC=...`。

**`云端返回 code=... ` / 状态一直是关机**
→ 椅子没联网或账号 token 过期。先确认官方 App 能控制；再重跑 `setup` 重新取 token。

**`网络错误`**
→ 电脑要能上外网（接口是 `https://iot3.xingzhuo.xyz`），公司网络/代理可能被拦。

**`setup` 里 adb 找不到**
→ `python3 rtchair.py setup --adb /path/to/adb`。


## 7. 离线模式（不连荣泰云）

已经打通：让椅子连到**路由器上的假阿里云 broker**，控制全在局域网内完成。

```bash
cd ..
./tools/offline_on.sh          # 开启离线模式（一次性）
./tools/offline_off.sh         # 恢复连荣泰云

cd cli
python3 rtchair.py mode local  # 切到离线模式
python3 rtchair.py status
python3 rtchair.py run programs/久坐救星.plan
python3 rtchair.py serve       # 手机控制面板，离线也一样用
```

详见 `docs/离线模式-使用说明.md`。

### 已接入 Home Assistant

HA 自定义集成已经装好（**32 个实体** + 自带「按摩椅」仪表盘）：开关/下拉/数值/传感器/6 个一键程序：

```bash
./tools/ha_deploy.sh     # 改了集成后一键重新部署到 HA
```

实体清单和自动化示例见 `docs/HA集成-使用说明.md`。

> 注：RT7709S 没有原生摇椅（Pro 型号才有）。集成里用「零重力整椅往返」做了个
> **摇椅模式（模拟）** 开关 + 后仰/回正秒数可调 + 腿部空间最大按钮。

> 另外还有一条只读的「局域网直连」通道（`rtchair_local.py`，抓 MCU 串口帧），
> 不依赖路由器和假云，可用于监控：`python3 rtchair_local.py monitor`。

## 6. 安全提示

- 别在无人看管时启动程序；老人、孕妇、骨质疏松、有伤在身的人按说明书使用
- 不要连续长时间运行，30 分钟上限是椅子本身的限制
- 这是非官方用法：属性值越界一般被椅子忽略，但请只使用本文列出的取值
