# 出厂默认参数（现场 broker 等）— 口径与做法

> 钟工 2026-09-30：「把现场用的 broker 地址作为出厂默认写进 prefs（量产/固化包里带上），
> 不依赖代码里的硬编码默认。」

## 1. 为什么要有这个机制

开源要求下，**代码里不能出现任何内网地址/账号**（`ConfigStore` 的旧默认值已清空）。
但现场设备要**开箱就能上 HA/Domoticz** —— 两者用一个折中解决：

> **出厂参数不进代码，走一份配置文件；app 首次启动把它落盘到 prefs，之后以 prefs 为准。**

这样：开源仓干净；量产只带一份 json；现场仍可用板内网页随时改。

## 2. app 侧行为（`src/storage/ConfigStore.cpp::applyFactoryDefaults`）

查找顺序（第一个存在的生效）：

```
/mnt/sdnand/panel-defaults.json     ← 量产/现场预置（推荐；74M rw 分区，重启仍在）
/mnt/extsd/panel-defaults.json      ← SD 卡
/res/etc/panel-defaults.json        ← 随固化包（update.img）一起进只读分区
```

- **只在 prefs 里还没配置 `sp_mqtt_server` 时读取**（prefs 优先，绝不覆盖现场已改的配置）
- 读到就把 `mqtt_server / mqtt_user / mqtt_pass / mqtt_en` **写入 prefs**（落盘），日志会打
  `ConfigStore: factory defaults applied from ... -> server=... (persisted to prefs)`
- 文件格式（键都可缺省）：

```json
{
  "mqtt_server": "mqtt://192.0.2.188:1883",
  "mqtt_user": "",
  "mqtt_pass": "",
  "mqtt_en": true
}
```

> 注：`mqtt_pass` 属于凭据，**进量产包前注意保密**（不要把带口令的 defaults 文件提交进开源仓）。

## 3. 工具：`tools/provision_factory_defaults.py`

```bash
# 生成
python tools/provision_factory_defaults.py gen --server mqtt://192.0.2.188:1883 -o panel-defaults.json
# 推给设备（放 /mnt/sdnand）
python tools/provision_factory_defaults.py push --devices 192.0.2.55,192.0.2.71 --file panel-defaults.json
# 已经在跑的机器：直接写 prefs（不依赖默认机制）
python tools/provision_factory_defaults.py prefs --devices 192.0.2.55 --server mqtt://192.0.2.188:1883
# 查看现状
python tools/provision_factory_defaults.py show --devices 192.0.2.55,192.0.2.71
```

样例文件：`tools/panel-defaults.sample.json`。

## 4. 量产/固化清单（新增一项）

1. 准备 `panel-defaults.json`（现场 broker 地址，必要时带账号口令）
2. 出 `update.img` 时把它放进 `/res/etc/`（随固件）**或**产线用 `push` 子命令写 `/mnt/sdnand/`
3. 设备首次开机 → 日志确认 `factory defaults applied ... persisted to prefs`
4. 现场如需改服务器：面板「运行模式 → HA」页扫码，用板内网页改（**prefs 优先，默认文件不再生效**）

## 5. 背景：这次的教训（2026-09-30）

- 旧代码用**写死的默认** `mqtt://192.0.2.188:1883` 兜底 → 面板"不配置也能上 HA"
- 开源化清掉该默认后，**没配过的 5 台立即从 HA 消失**（另有 2 台被测试时指到了临时 broker）
- 现场修法：用板内网页把 broker 写回；长效机制：本文件的出厂默认机制
- 遗留待办：`base-utility` 包里 `releaseAll()` 尾部的 `system("echo 3 > /proc/sys/vm/drop_caches")`
  会被视频段循环每 ~10 s 触发一次（load 打满、网络抖动）→ 建议改播放路径不每次释放，或推厂商修
