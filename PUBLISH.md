# 发布到 GitHub —— 步骤与待拍板事项

> 发版目录：`release/SmartPanel/`（**已脱敏**：内网 IP → `192.0.2.x` 示例段、设备 ID → `PANEL-SAMPLE01`、
> 已移除依赖 `accessKey`、已剔除内部资料与构建产物）

## 1. 目录内容（发版白名单）

```
SmartPanel/
  src/            应用源码（Main / activity / logic / device / network / scene / storage / wall / system / mp_transfer…）
  ui/             *.json 布局（含 ui/_gen 生成脚本；*.ftu 为构建产物，不入仓）
  resources/      UI 图片资源
  font/           中文字库（注意 OFL 声明，见 THIRD_PARTY_LICENSES.md）
  tools/          多屏拼接切块/分发、出厂默认预置、无设备回归冒烟
  docs/           发布说明 / 整机说明书 / 多屏拼接 / HA 配置 / Domoticz 兼容 / 出厂默认
  Manifest.xml    依赖声明（**accessKey 已移除**，simple-player 需自行申请）
  README.md  LICENSE(MIT)  THIRD_PARTY_LICENSES.md  .gitignore
```

## 2. 发布步骤

```bash
cd release/SmartPanel
git init -b main
git add -A
git commit -m "SmartPanel: Z20 智能面板（HA 接入 / 多屏拼接 / 相册）— 首次开源"
git remote add origin <你的仓库地址>       # GitHub / Gitee
git push -u origin main
```

> 发布前建议再跑一次静态扫描（本仓已无内网地址/凭据；如需复核）：
> `grep -rnE "192\.168\.|PANEL-[0-9A-F]{8,}|accessKey" .`

## 3. 待拍板（产品/法务）

| # | 事项 | 现状 |
|---|---|---|
| D3 | 是否附带预编译产物 / `update.img` 固件 | 建议**只开代码**（当前目录即如此） |
| D4 | 托管与流程：GitHub 还是 Gitee？是否接受外部 PR？issue 模板 | 待定 |
| D5 | 品牌口径：README/截图里出现公司名、型号 `SW48480040D1`、`Z20` 是否 OK | 当前保留了公司信息与型号 |
| V1 | **FlyThings SDK / EasyUI / mi-module / simple-player** 能否随工程分发（含授权 key 的包） | ⚠️ 需厂商口径；当前只声明依赖、不含授权 |
| V2 | `ffmpeg` 构建选项（LGPL/GPL）与再分发义务 | ⚠️ 待确认 |
| V3 | 字库：思源黑体 OFL 声明 + 自造字库可否开源 | ⚠️ 待确认 |

## 4. 本次已同步修复/整理的内容（可写进 Release Notes）

- **HA 接入**：标准 MQTT Discovery 自动出 3 个开关；板内网页扫码配置 broker/令牌（含 eth0 回退、无 IP 时提示）
- **多屏拼接**：竖排/横排实拍口径效果图、切块工具网页版、`seam_w` 丢弃口径（本组 52 px）
- **相册**：小程序二维码改为**控件现场生成**（原 128 px 位图压缩糊）
- **继电器状态安全**（2026-09-30 现场问题）：`init()` 幂等 + 无存档不回写硬件 + 命令严格校验（重连/断网不改灯）
- **出厂默认机制**：`panel-defaults.json` → 首次启动落盘 prefs（代码不含内网地址）
- **文档**：`docs/发布说明.md`（含真机截图与效果图）、`docs/FACTORY-DEFAULTS.md`、`docs/DOMOTICZ-COMPAT.md`、`docs/HA-CONFIG-WEB.md`
