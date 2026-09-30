# SmartPanel — 86 盒智能面板（FlyThings / SigmaStar SSD20x）

一块装在 86 盒里的 **4 寸 480×480 Linux 触摸面板**：3 路 10 A 继电器、情景联动、
可当 Home Assistant 的终端、也能自己当本地主机；外加 15 秒无操作变时钟/相框、
夜景整块熄屏、一键 180° 倒装、4 块拼一堵视频墙。

> 开源准备中（第一个开源整个 SmartPanel 的项目）。**许可与脱敏清单见 `docs/OPENSOURCE-READINESS.md`**，
> 未清干净之前请勿公开发布代码/截图。

---

## 1. 功能

| 模块 | 说明 |
|---|---|
| 3 路继电器 | 每路可改名（客厅灯/灯带/茶台），面板触摸、情景联动、HA 下发三路状态同源（`RelayManager` 唯一事实源） |
| 三种运行模式 | ① **HA 模式**：接外部 broker（MQTT Discovery 自动出 3 个 switch 实体）② **本地主机**：板内起 MQTT broker，同网段从机/小程序直连 ③ **本地从机**：连主机 broker |
| 情景 | 面板内置情景表（回家/离家/睡眠/休闲）；HA 侧可下发情景清单与触发 |
| 时钟 / 相册 | 空闲 15 s 进入时钟；相册可扫小程序码传图（TF 卡/U 盘素材） |
| 熄屏时段 | 例 20:00–08:00 整块黑屏，触摸唤醒 |
| 倒装 | 一键 180°（整屏 + 触发层一起转），现场装机不用拆 |
| 多屏拼墙 | 同一视频按屏切段，相位对齐 + 校时；也支持一组多视频轮播；**不依赖外部服务器**（主机广播 epoch） |
| 本地中枢 | 板内独立 MQTT broker 服务（`projects/z20_local_hub`）：app 拉起、QoS1/Will/retained、RSS ~1 MB |

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
                           MiniBroker（内嵌 broker，回退用）、
                           LocalBrokerService（拉起板内 broker 服务）、PanelLink、TcpReceive
  storage/ConfigStore      全部配置/持久化（prefs）
  mp_transfer/             小程序传输
ui/                        *.json 布局 + *.ftu 产物
resources/images/          UI 图片资源
font/                      中文字库（裁剪字库，注意设备字库不支持 emoji/特殊符号）
docs/                      设计/说明书/开源准备
```

## 3.1 HA / MQTT 服务器配置（扫码，不写死）

外接 broker 的地址、用户名、令牌**没有任何内置默认值**。在面板上选「设置 → 运行模式 → HA 模式」，
卡片下方会出现二维码：手机扫码打开板内网页（`http://<面板IP>:8080/<口令码>/`），把长令牌直接粘进去点保存，
面板立刻按新配置重连。令牌只落设备本地 prefs，不上传。细节见 `docs/HA-CONFIG-WEB.md`。

## 4. 构建与部署

```bash
fun install                                   # 拉依赖（改 Manifest 后必须重跑）
fun build -p Z20                              # 编译 → .fun/z20 或 .fsc/z20 下 libzkgui.so
fun pack -p Z20 --startup-dir /res --release-version 1.0.N   # 出 update.img（U 盘/TF 升级）
```

调试期热替换（不动系统分区）：

```bash
adb push update_lib/libzkgui.so /tmp/lib/libzkgui.so
# /tmp/EasyUI.cfg 里 startupLibPath 指到 /tmp/lib/libzkgui.so（注意：**不能带 BOM**，带 BOM 会被忽略）
adb shell "setprop ctl.restart zkswe"
```

⚠️ 设备端排查前先 `adb push tools/busybox/bin/z20/busybox /tmp/busybox`（设备 shell 没有 free/grep/nohup 等）。

## 5. MQTT 主题约定

```
smartpanel/<deviceId>/status                     设备状态 JSON（retained）
smartpanel/<deviceId>/switch/relay_<1..3>/state   继电器状态 ON/OFF（retained）
smartpanel/<deviceId>/switch/relay_<n>/command    外部命令 ON/OFF → 面板执行
smartpanel/broadcast/scene                        情景激活（payload = 情景名）
smartpanel/broadcast/scenes                       情景定义全集（retained）
homeassistant/switch/<uid>_<relay>/config         HA Discovery（HA 模式）
```

## 6. 验收

- 面板 UI 像素级：`tools/ui_tools/ui_diff.py`（±2 容差）
- 板内 broker 服务：`projects/z20_local_hub/tools/{acceptance,boundary_acceptance,app_integration_acceptance}.py`
- 多设备跑批：MCP `flythings_test_run`（用例 JSON + logcat 断言）

## 7. 开源状态

- [x] **许可：MIT**（钟工 2026-09-30 拍板「宽松的 MIT」）—— 见 `LICENSE`；
      **板内 broker 服务 `projects/z20_local_hub` 一起开源**，同 MIT
- [x] 代码内凭据/内网信息：外接 broker 地址、MQTT 口令、小程序 AppID 的默认值**已清空**；
      HA 服务器改由「扫码 + 板内网页」配置 ☞ `docs/HA-CONFIG-WEB.md`
- [ ] 其余脱敏（docs/reports 里的真机 IP、内部工程名）→ 清单见 `docs/OPENSOURCE-READINESS.md`
- [ ] 第三方依赖许可核对（FlyThings SDK / EasyUI / rapidjson / mqtt-cxx / mbedtls / curl 等）
- [x] 示例配置不指向任何内网：默认空配置，用户自行填 / 扫码
