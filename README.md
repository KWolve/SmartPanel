# SmartPanel — 86 盒智能面板（FlyThings / SigmaStar SSD20x）

**中文** ｜ [English](README.en.md)

一块装在 86 盒里的 **4 寸 480×480 Linux 触摸面板**：3 路 10 A 继电器、情景联动、
可当 **Home Assistant 终端**、也能自己当本地主机；外加空闲变时钟/相框、夜景整块熄屏、
一键 180° 倒装、**多块拼成一堵视频墙**。

> 🛒 **整机购买（淘宝）**：<https://item.taobao.com/item.htm?id=650865599184&skuId=5500508256776>

> 许可以为 **MIT**（见 `LICENSE`）。第三方依赖与再分发口径见 `THIRD_PARTY_LICENSES.md`，
> 发布流程与待拍板事项见 `PUBLISH.md`。

---

<table>
  <tr>
    <td align="center"><img src="docs/shots/01_home.png" width="150"><br><sub><b>主界面</b><br>3 路继电器 + 情景</sub></td>
    <td align="center"><img src="docs/shots/02_album_qr.png" width="150"><br><sub><b>相册</b><br>扫码传图</sub></td>
    <td align="center"><img src="docs/shots/03_settings.png" width="150"><br><sub><b>设置</b><br>功能一览·全部功能入口</sub></td>
    <td align="center"><img src="docs/shots/04_screensaver_video.png" width="150"><br><sub><b>屏保</b><br>视频/图片轮播</sub></td>
    <td align="center"><img src="docs/shots/05_ha_config_qr.png" width="150"><br><sub><b>HA 配置</b><br>扫码填服务器与令牌</sub></td>
  </tr>
  <tr>
    <td colspan="5" align="center"><img src="docs/shots/10_wall_3split.png" width="860"><br><sub><b>三屏拼接</b> · 同一视频按屏切段，相位对齐 + 校时（1×3 横排，机间丢弃 52 px，屏保时钟在最右屏右上角）</sub></td>
  </tr>
</table>

---

## 0. 依赖：FlyThings MCP（**release 版**）

本工程的二次开发（编译/调试/出包/知识库/设备工具）依赖 **FlyThings MCP**，
其 **release 版本单独维护、单独发布**，本仓只引用、不复制：

| 用途 | 位置 |
|---|---|
| **release 版（用户获取/安装处）** | `https://github.com/KWolve/FlyThingsMCP` |
| 国内镜像（Gitee） | `https://gitee.com/Kwolve/flythingsmcp_release` |
| 本机路径（同工作区校验用） | `tools/FlyThings_mcp_release/` |

安装与接入方式以该 release 仓的 README 为准（把 MCP 接入你的 AI 客户端即可）。

---

## 1. 功能

| 模块 | 说明 |
|---|---|
| 3 路继电器 | 每路可改名（客厅灯/灯带/茶台），面板触摸、情景联动、HA 下发三路状态同源（`RelayManager` 唯一事实源） |
| 三种运行模式 | ① **HA 模式**：接外部 broker（MQTT Discovery 自动出 3 个 switch 实体）② **本地主机**：板内起 MQTT broker，同网段从机/小程序直连 ③ **本地从机**：连主机 broker |
| 情景 | 面板内置情景表（回家/离家/睡眠/休闲）；HA 侧可下发情景清单与触发 |
| 时钟 / 相册 | 空闲 15 s 进入时钟/相册；**扫码传图**（二维码由控件现场生成） |
| 熄屏时段 | 例 20:00–08:00 整块黑屏，触摸唤醒 |
| 倒装 | 一键 180°（整屏 + 触发层一起转），现场装机不用拆 |
| 多屏拼墙 | 同一视频按屏切段，**相位对齐 + 校时**；支持一组多视频轮播；不依赖外部服务器（主机广播 epoch） |
| 本地中枢 | 板内独立 MQTT broker 服务：app 拉起、QoS1/Will/retained、RSS ~1 MB |

## 2. 硬件 / 平台

- 平台：**Z20 / SigmaStar SSD201·SSD202D**（Cortex-A7 双核 1.2 GHz，内置 128 MB DDR3，外挂 16 MB NOR + 128 MB SD NAND）
- 屏：480×480（同系 720×720）；整机型号 SW48480040D1
- 电源：AC220V / DC9-24V；RS485 + 百兆以太网；3 路继电器 10 A
- 系统：FlyThings V2.1 + EasyUI（`/res` 只读 squashfs，`/data` 512 KB，`/mnt/sdnand` 74 MB rw）

## 3. 目录结构

```
src/
  Main.cpp                 程序入口
  activity/                主 Activity
  logic/                   页面逻辑（home/main/settings/scenes/album/video/wall/off…）
  device/                  RelayManager（继电器唯一事实源）、SensorManager
  network/                 MqttBridge（HA 模式）、LocalLink（本地主/从机）、
                           MiniBroker（内嵌 broker，回退）、LocalBrokerService、
                           WebConfigServer（板内配置网页）、PanelLink、TcpReceive
  storage/ConfigStore      全部配置/持久化（prefs）
  wall/                    多屏拼接（WallLink 时钟对齐 / WallPlayer 播放）
ui/                        *.json 布局 + *.ftu 产物（ftu 由 fui pack 生成）
resources/images/          UI 图片资源
font/                      中文字库（裁剪字库：不支持 emoji / 特殊符号）
tools/                     多屏切块（网页版）、出厂默认预置、无设备回归冒烟
docs/                      发布说明 / 整机说明书 / 多屏拼接 / HA 配置 / Domoticz 兼容 / 出厂默认
```

## 3.1 HA / MQTT 服务器配置（扫码，不写死）

外接 broker 的地址、用户名、令牌**没有任何内置默认值**（代码里不带内网地址）。
在面板上选「设置 → 运行模式 → HA 模式」，卡片下方出现二维码：手机扫码打开**板内网页**
（`http://<面板IP>:8080/<口令码>/`），把长令牌直接粘进去点保存，面板立刻按新配置重连。
令牌只落设备本地 prefs，不上传。细节见 `docs/HA-CONFIG-WEB.md`。

**量产/出厂**：把 `panel-defaults.json`（现场 broker 等）放进 `/mnt/sdnand` 或随固件放 `/res/etc`，
设备首次启动自动落盘到配置 —— 见 `docs/FACTORY-DEFAULTS.md`。

## 4. 构建与部署

```bash
fun install                                   # 拉依赖（改 Manifest 后必须重跑）
fun build -p Z20                              # 编译 → .fun/z20 或 .fsc/z20 下 libzkgui.so
fun pack -p Z20 --startup-dir /res --release-version 1.0.N   # 出 update.img（U 盘/TF 升级）
```

调试期热替换（不动系统分区，断电回落原厂）：

```bash
adb push libzkgui.so /tmp/lib/libzkgui.so
# /tmp/EasyUI.cfg 里 startupLibPath 指到 /tmp/lib/libzkgui.so（**不能带 BOM**，带 BOM 会被忽略）
adb shell "setprop ctl.restart zkswe"
```

⚠️ 设备端排查前先 `adb push tools/busybox/bin/z20/busybox /tmp/busybox`（设备 shell 没有 free/grep/nohup 等）。

## 5. MQTT 主题约定

```
smartpanel/<deviceId>/availability                  online / offline（LWT）
smartpanel/<deviceId>/status                        设备状态 JSON（retained）
smartpanel/<deviceId>/switch/relay_<1..3>/state     继电器状态 ON/OFF（retained）
smartpanel/<deviceId>/switch/relay_<n>/command      外部命令 ON/OFF → 面板执行
smartpanel/broadcast/scene                          本机模式：情景激活
smartpanel/ha/scenes                                HA 下发情景清单（retained）
homeassistant/switch/<uid>_<relay>/config           HA Discovery（HA 模式）
```

## 6. 多屏拼接（网页端切块工具）

```bash
python tools/video_wall/web/server.py --port 8796     # 浏览器打开 http://<PC>:8796/
```
拖框选画面区域（每屏可独立拖动）→ 导出 `c1/seg_1..N.mp4 + playlist.json` → **一键分发**到各屏。
本组实拍口径：**横排 1×3、机间丢弃 52 px、屏保时间在最右屏右上角**（效果图见 `docs/发布说明.md`）。

## 7. 验收

- 面板 UI 像素级：`tools/ui_tools/ui_diff.py`（±2 容差）
- 板内网页配置：`tools/webcfg_test/`（x86 替身冒烟，无需设备）
- 多设备跑批：MCP `flythings_test_run`（用例 JSON + logcat 断言）

## 8. 开源状态

- [x] **许可：MIT**（见 `LICENSE`）；板内 broker 服务同 MIT
- [x] 代码内凭据/内网信息：外接 broker 地址、MQTT 口令、小程序 AppID 默认值**已清空**
- [x] 示例配置不指向任何内网：默认空配置，用户自行扫码配置或走出厂默认文件
- [x] 第三方依赖清单与许可：`THIRD_PARTY_LICENSES.md`（含待确认项）
- [x] 发布资料与脱敏记录：`PUBLISH.md`；发布说明：`docs/发布说明.md`
