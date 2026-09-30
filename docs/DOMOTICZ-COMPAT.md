# Domoticz 兼容性（实测结论，2026-09-30）

> 起因：钟工「domoticz 这个功能目前是完整的吗？比如有传感器是否可以接入。」
> 结论先行：**面板 → Domoticz 的开关方向已实测闭环**；**传感器接入已实测可行**（用一个模拟网关发的标准 HA discovery 验证）；
> **情景那套是我们自定义主题 + HA 自动化，Domoticz 没有等价物**；**面板目前不接收天气等回传数据**。

## 1. 协议口径（源码级确认）

Domoticz 的 `hardware/MQTTAutoDiscover.{h,cpp}` 实现的就是 **Home Assistant MQTT Discovery**：

- 订阅 `<前缀>/#`（前缀可配，**实测放在 `extra` 字段第 4 段**，`;;;homeassistant`），我们发的
  `homeassistant/switch/<uid>_relay_N/config` 它能收到
- 支持的 component 白名单：`sensor` `binary_sensor` `switch` `light` `lock` `select` `cover`
  `climate` `button` `number` `device_automation` `fan` `text`
- 同时认长键名与缩写键（`unit_of_measurement`/`unit_of_meas`、`brightness_value_template`/`bri_val_tpl`…）
  → 我们 `publishDiscovery()` 用的缩写风格无需改
- 按 `device_class` / 单位映射成 Domoticz 原生类型（Lux / Voc / Voltage / Current / Electric / Kwh / Baro / General-Custom…）

## 2. 建这个硬件（踩坑记录）

Domoticz 加硬件用 JSON API，**htype = 125**（`HTYPE_MQTTAutoDiscovery`，见源码 `main/RFXNames.cpp`
+ `test/python/test_calibration.py` 注释）。两个必踩的坑：

1. **不能只给 address/port** —— 校验要求 `mode1` 非空（TLS 版本），只给地址会返回 `{"status":"ERR"}`
2. **discovery 前缀走 `extra` 字段**，格式 `<CA>;<..>;<..>;<prefix>`，所以传 `extra=;;;homeassistant`

可抄的命令：

```
curl -s "http://127.0.0.1:8081/json.htm?type=command&param=addhardware&htype=125&name=SmartPanel-AD\
&address=<broker>&port=1883&username=&password=&Mode1=0&extra=;;;homeassistant&enabled=true"
```

> 顺便记下几个相邻编号（都是实测撞出来的）：119=OctoPrint(MQTT)、126=RFLink MQTT、93=I2C_PCF8574、96=I2C_BME280。

## 3. 实测结果（108 + 71 + 模拟传感器，一台 broker）

| 项 | 结果 |
|---|---|
| 面板 108（PANEL-SAMPLE01） | Domoticz 建出 **3 个 Light/Switch**：客厅灯(On) / 卧室灯(On) / 灯带(Off)，状态与面板一致 |
| 面板 71（PANEL-SAMPLE01） | 同样建出 **3 个 Light/Switch**（PANEL-zhong 组） |
| **反向控制** | Domoticz 点 `switchlight idx=3 On` → 面板发布的 `relay_3/state` 由 **OFF→ON**；点 Off → 回 OFF（面板真的执行了） |
| **传感器接入** | 模拟网关发 `homeassistant/sensor/<uid>_{temp,hum}/config`（`dev_cla=temperature/humidity`、`unit_of_meas=°C/%`）→ Domoticz 建出 **Temp + Humidity** 实体，数值随上报更新（25.2 °C, 48 %） |
| 可用性 | 面板 LWT 发 `availability`，Domoticz 侧按 `avty_t` 订阅（未做断线场景的专项验证） |

## 4. 缺口（要说清楚的）

- **情景**：面板拉 `smartpanel/ha/scenes` 清单、点情景发 `ha_scene/set`，靠 HA 侧自动化执行 → Domoticz 没等价物，
  要用 **dzVents/Lua** 自己接；或我们把情景改走标准 MQTT 主题，两边都能吃
- **回传方向（网关 → 面板）**：面板在 HA 模式只订阅
  `prefix/switch/+/command`、`prefix/scene/+/command`、`smartpanel/ha/scenes`、`smartpanel/ha/active_scene`
  —— **没有任何天气/传感器回传**。屏保上的温湿度/天气是 `PanelLink` TCP 推送（`{"cmd":"weather","text":"晴 26C"}`，
  小程序/网关推）+ `SensorManager` 预留的 HTTP 天气接口
- **传感器数据源**：面板本体没有温湿度传感器（P3 决策，相关 discovery 已清）；要「面板自己发传感器」需先定数据源
- 未验：TLS、用户名/口令鉴权、断线重连与实体不可用（availability）场景

## 5. 「网关有没有天气数据」——有

Domoticz 侧可持有天气数据的两种方式：

1. **内置天气服务硬件**（源码 `ValidateHardware` 里列出的类型）：Weather Underground / DarkSky /
   VisualCrossing / AccuWeather / OpenWeatherMap —— 填 API key 即由 Domoticz 定时拉取
2. **收 MQTT 传感器**：任何网关按 HA discovery 报温度/湿度/气压/雨量 → 变成 Domoticz 的天气类设备

对外取用：JSON API（`/json.htm?type=command&param=getdevices`）或 MQTT state topic。
**面板要用的话**，只需在 `MqttBridge::subscribeAll()` 里加一条订阅 + 屏保项接线（小改动），
这属于「网关 → 面板」方向的新能力，目前没有。

## 6. 复现脚本

`temp/domoticz-spike/`（本机 spike，不进交付）：

| 脚本 | 作用 |
|---|---|
| `docker-compose.yml` | mosquitto(11883) + domoticz(8081，`EXTRA_CMD_ARG=-nowwwpwd` 免 web 口令) |
| `reset.sh` | 洗白重建 + 建 htype=125 硬件 |
| `panel_to_dz.sh` / `panel71.sh` | 把面板指到 spike broker 并回读实体 |
| `verify_loop.py` | 反向控制 + 传感器模拟（paho-mqtt） |
