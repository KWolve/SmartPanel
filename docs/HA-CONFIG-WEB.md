# HA 服务器配置（扫码用手机填）

> 钟工 2026-09-30：「HA 服务器的地址和 token 现在是写死的，这个点需要改成可以配置的。
> 考虑到 token 内容比较多输入麻烦，建议一样提供一个内置的网页通过手机扫码配置。」

## 1. 结论

- **不再写死**：`ConfigStore` 里外接 broker 的服务器 / 用户名 / 密码（令牌）默认**全为空**，
  代码里已无任何内网地址与账号（开源版专用）。老设备升级后若 prefs 里已有值，继续沿用。
- **手机扫码配置**：面板「设置 → 运行模式 → HA 模式」卡片选中后，下方出现二维码；
  手机扫码打开**板内网页**（`http://<面板IP>:8080/<口令码>/`），把长 token 直接粘进去点保存。
- 保存即生效：写入 prefs 后立刻 `MqttBridge::stop() + init()` 按新配置重连（失败由 tick 退避续试）。

## 2. 面板侧（480×480）

```
运行模式页（mode.ftu）
  [ HA 模式 ] [ 本地主机 ] [ 本地从机 ]     ← 选 HA
  ┌──────┐  扫码配置 HA 服务器            ← 仅 HA 模式显示
  │ 二维码│  http://192.0.2.50:8080/K7XM2P/
  └──────┘  手机扫码后粘贴服务器与令牌
  [        保存        ]
```

- 二维码内容 = 板内网页地址（含本机 IP + 每次首启生成后持久化的 6 位口令码）。
- 「主机 IP」输入行是给**本地从机**用的，HA 模式下自动隐藏（两种模式互斥显示）。
- 二维码只在**内容变化时**重新生成（IP 变了才重算，QR 重算开销大；1s 心跳里比对）。

## 3. 网页侧（WebConfigServer，`src/network/WebConfigServer.{h,cpp}`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/<code>/` | 配置页（手机友好，深色，纵向表单） |
| POST | `/<code>/save` | 表单保存（`application/x-www-form-urlencoded`）→ 结果页 |
| GET | `/<code>/status` | 状态 JSON：deviceId / ip / runMode / enabled / server / user / hasPassword / connected / prefix |

- 表单字段：服务器地址、用户名（可留空）、密码/令牌（textarea，**自动去掉换行与空格** —— 粘贴 HA 令牌常见带换行）、启用 HA 连接。
- 地址归一化：填 `192.0.2.50` → `mqtt://192.0.2.50:1883`；填 `192.0.2.50:8883` → 补 `mqtt://`。
- 页面自带 3 s 轮询 `status`，保存后能直接看到「已连接 / 未连接（重试中）」。
- 页面同时显示设备 ID 与主题前缀（`smartpanel/<deviceId>`），方便在 HA 侧核对。

## 4. 端口与安全口径

- 端口 **8080**（`:8084` 是 zkmqtt 状态页，`:9000` 是相册上传，互不冲突）。
- **IP 取用口径**：`wlan0` → `eth0`（Z20 有百兆网口，客户可能走网线）→ 其它非回环网卡；
  都没 IP 时面板上不显示二维码，改成「等待面板联网（WiFi / 网线）…」。
  （待注意：`NetKeeper_localIp()` 只读 wlan0，设置页的「WiFi 行」在纯网线场景会显示未连接，与本功能无关，待单独收）
- 明文 HTTP、无 TLS，面向**局域网运维**，与 MQTT 明文 1883 同一安全档位。
- 口令码（`ConfigStore::webCfgCode()`，6 位、去掉易混字符 I/O/0/1、首启生成后持久化）只挂在 URL 路径上，
  作用是**防止同网段无关设备随手打开乱改**；**它不是鉴权**，同网段拿到 URL 的人即可读写配置（文档已明说）。
- 服务在 app 启动时（`onEasyUIInit`）拉起，常驻监听；令牌只落设备本地 prefs，不上传任何服务器。

## 5. 无设备回归（推荐每次改完都跑）

`tools/webcfg_test/` 是 x86 替身冒烟：用内存版 `ConfigStore` 编译真实的 `WebConfigServer.cpp`，
起服务后 curl 走完「读页 → 存 → 读回」全链路。

```bash
cd projects/SmartPanel_HA/tools/webcfg_test
g++ -std=c++14 -Wall -I . -I ../../src stubs.cpp ../../src/network/WebConfigServer.cpp -o /tmp/webcfg -lpthread
bash test.sh        # 5 步：长令牌粘贴保存 / 地址归一化+status / 页面回填 / 口令码错->404 / 停机
```

实测（2026-09-30）：

```
1) 长令牌（带换行空格）POST -> HTTP 200「配置已写入，面板正在连接服务器。」
2) server 192.0.2.50 -> mqtt://192.0.2.50:1883；hasPassword=true；connected=true
3) 重开页面回填：server/user/pass 与勾选状态全部正确
4) 口令码错误 -> HTTP 404
```

真机侧同样口径：`fun build -p Z20` 53/53 通过；`check_all.py` 对 `ui/mode.json` 无新增问题。

IP 回落路径也在替身里验过：把替身的 `NetKeeper_localIp()` 置空（模拟只插网线/没 wlan0），
`pageUrl()` 正确回落到 `eth0` 的地址（WSL 里实测拿到 `http://192.0.2.188:18080/AB12CD/`）。

## 6. 后续（未做，按需）

- 网页加「测试连接」按钮（连一下 broker 立即回报，不用等面板重连）。
- 可选：只在配置页显示时监听（进一步收窄暴露面）。
- HA 侧自动发现面板 IP 的 mDNS 广播（现在是扫码，够用）。
