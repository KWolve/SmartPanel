# 第三方许可与依赖声明（THIRD_PARTY_LICENSES）

本仓代码（应用层 + 板内 MQTT 服务）为 **MIT**（见 `LICENSE`）。
下列第三方组件按各自许可使用；**发布前需逐项确认再分发合规性**（标 ⚠️ 者需产品/法务口径）。

## 1. 平台运行时（FlyThings SDK / EasyUI 等预编译包）

| 组件 | 用途 | 许可/来源 | 备注 |
|---|---|---|---|
| `easyui` ^2.2.0 | UI 运行时 + 控件 | ⚠️ 厂商预编译包 | **能否随开源工程分发需厂商口径**；本仓 `Manifest.xml` 只声明依赖 |
| `log` / `zkhardware` / `zknet` | 日志 / GPIO / 网络 | ⚠️ 厂商包 | 同上 |
| `base-utility` ^10.8.5 | 基础库（含文件/播放辅助） | ⚠️ 厂商包 | 同上；注意其释放路径含 `drop_caches` 调用（见 README 已知问题） |
| `ntp` 2.1.1 | 校时（多屏拼接前置） | ⚠️ 厂商包 | 同上 |
| `mi-module` 5.0.2 / `mi_*` | SigmaStar MI 显示/解码 | ⚠️ 芯片厂 SDK | 同上 |
| `simple-player` ^4.0.1 | 视频播放内核 | ⚠️ 厂商包（**需 accessKey 授权**） | **本仓已移除 `accessKey`**；部署方需自行向厂商申请 |

## 2. 第三方开源库（随依赖包引入）

| 组件 | 用途 | 许可 |
|---|---|---|
| `rapidjson` 1.1.0（本仓 `src/rapidjson/` 内置副本） | JSON | MIT（保留版权声明） |
| `mqtt-cxx` ^3.2.0 | MQTT 客户端封装 | 按其包内声明（EPL/EDL 系，需核对） |
| `paho-mqtt3as` ^1.3.13 | MQTT 客户端（SSL） | EPL-1.0 / EDL-1.0 |
| `mbedtls` ^3.6.5 | TLS | Apache-2.0 |
| `openssl` 1.1.1-w | 加密/TLS | OpenSSL License（含原版 SSLeay 条款） |
| `curl` 8.12.1-mbedtls / `curl-cxx` ^10.0.3 | HTTP | curl license（MIT/X 系） |
| `z` 1.2.11 | zlib | zlib license |
| `cares` 1.17.2 | 异步 DNS | MIT |
| `ffmpeg` 4.1.9-configure3 | 解封装/转封装（多屏拼接） | ⚠️ **LGPL/GPL 视构建而定**，需确认 configure 选项与再分发义务 |

## 3. 字库

| 字体 | 用途 | 许可 |
|---|---|---|
| `HanSans-Medium.ttf` / `HanSansLight.ttf` | 中文界面 | ⚠️ 思源黑体（SIL OFL 1.1）→ **需附 OFL 声明** |
| `zkswe-hans-common.ttf` | 裁剪字库（设备用） | ⚠️ 自造字库，可否开源需内部确认 |

## 4. 板内 MQTT 服务（另一仓库）

`z20_local_hub`（`zkmqtt`，单文件 C）为**自研**，与本项目同许可（MIT），见对应仓库。

---

_如需生成完整 NOTICE 文件或许可原文合集，可在发布前用脚本从各依赖包内 `LICENSE*` 汇总。_
