#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
provision_factory_defaults.py -- 出厂参数预置（现场 broker 等）

钟工 2026-09-30 口径：**代码里不带任何内网地址**（开源要求），但现场设备要"开箱就能上 HA/Domoticz"。
做法：出厂/量产时把一份 `panel-defaults.json` 放进设备，app 首次启动（prefs 尚未配置时）
读入并**落盘到 prefs**，之后以 prefs 为准（现场也能用板内网页再改）。

查找顺序（app 侧实现，见 src/storage/ConfigStore.cpp::applyFactoryDefaults）：
    /mnt/sdnand/panel-defaults.json -> /mnt/extsd/panel-defaults.json -> /res/etc/panel-defaults.json

用法：
    # 1) 生成一份 defaults 文件（也可手工写）
    python provision_factory_defaults.py gen --server mqtt://192.0.2.188:1883 -o panel-defaults.json

    # 2) 推给设备（放 sdnand，重启后仍在；也可随固化包放进 /res/etc）
    python provision_factory_defaults.py push --devices 192.0.2.55,192.0.2.71 --file panel-defaults.json

    # 3) 直接写 prefs（不依赖 app 的默认机制；用于已经在跑的机器）
    python provision_factory_defaults.py prefs --devices 192.0.2.55 --server mqtt://192.0.2.188:1883

    # 4) 查看当前状态
    python provision_factory_defaults.py show --devices 192.0.2.55,192.0.2.71
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ADB = os.environ.get(
    "ADB",
    r"C:\Users\zkswe\.openclaw\workspace\sim\tools\adb.exe",
)
DEFAULTS_REMOTE = "/mnt/sdnand/panel-defaults.json"


def adb(serial, *args, timeout=120, check=False):
    cmd = [ADB, "-s", serial] + list(args)
    # Windows 默认 GBK 解码会在 adb 输出含非 GBK 字节时报 UnicodeDecodeError -> 显式 utf-8 + replace
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError("adb failed: %s\n%s\n%s" % (cmd, p.stdout, p.stderr))
    return p.stdout


def shell(serial, cmd, timeout=120):
    return adb(serial, "shell", cmd, timeout=timeout)


def gen(args):
    data = {"mqtt_server": args.server, "mqtt_user": args.user, "mqtt_pass": args.password,
            "mqtt_en": True}
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("written:", args.out)
    print(json.dumps(data, ensure_ascii=False))


def push(args):
    devs = [d.strip() for d in args.devices.split(",") if d.strip()]
    for d in devs:
        serial = d if ":" in d else d + ":5555"
        adb(serial, "connect", serial)
        shell(serial, "mkdir -p /mnt/sdnand")
        out = adb(serial, "push", args.file, DEFAULTS_REMOTE, timeout=300)
        print("  %-22s pushed -> %s" % (d, DEFAULTS_REMOTE))
        print("     ", shell(serial, "cat %s" % DEFAULTS_REMOTE).strip().replace("\n", " "))


def _prefs_path(serial):
    return "/data/preferences.json"


def prefs(args):
    devs = [d.strip() for d in args.devices.split(",") if d.strip()]
    for d in devs:
        serial = d if ":" in d else d + ":5555"
        adb(serial, "connect", serial)
        # 拉下来改完再推回去（设备端没有 jq/sed，稳一点）
        tmp = os.path.join(tempfile.gettempdir(), "prefs_%s.json" % d.replace(":", "_"))
        adb(serial, "pull", _prefs_path(serial), tmp, timeout=120)
        with open(tmp, encoding="utf-8") as f:
            doc = json.load(f, object_pairs_hook=dict)
        doc["sp_mqtt_en"] = True
        doc["sp_mqtt_server"] = args.server
        doc["sp_mqtt_user"] = args.user
        doc["sp_mqtt_pass"] = args.password
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=3)
        adb(serial, "push", tmp, _prefs_path(serial), timeout=120)
        print("  %-22s prefs updated (server=%s)" % (d, args.server))


def show(args):
    devs = [d.strip() for d in args.devices.split(",") if d.strip()]
    for d in devs:
        serial = d if ":" in d else d + ":5555"
        adb(serial, "connect", serial)
        raw = shell(serial, "cat %s 2>/dev/null" % _prefs_path(serial))
        keys = [l.strip() for l in raw.splitlines() if "sp_mqtt" in l or "sp_web_cfg_code" in l]
        f = shell(serial, "cat %s 2>/dev/null" % DEFAULTS_REMOTE).strip()
        print("===== %s =====" % d)
        for k in keys:
            print("   prefs:", k)
        print("   defaults file:", f if f else "(none)")


def main():
    ap = argparse.ArgumentParser(description="出厂参数预置（broker 等）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="生成 panel-defaults.json")
    g.add_argument("--server", required=True, help="如 mqtt://192.0.2.188:1883")
    g.add_argument("--user", default="")
    g.add_argument("--password", default="")
    g.add_argument("-o", "--out", default="panel-defaults.json")
    g.set_defaults(func=gen)

    p = sub.add_parser("push", help="把 defaults 文件推到设备 /mnt/sdnand")
    p.add_argument("--devices", required=True, help="逗号分隔，如 192.0.2.55,192.0.2.71")
    p.add_argument("--file", required=True)
    p.set_defaults(func=push)

    pr = sub.add_parser("prefs", help="直接写 prefs（已运行的机器用）")
    pr.add_argument("--devices", required=True)
    pr.add_argument("--server", required=True)
    pr.add_argument("--user", default="")
    pr.add_argument("--password", default="")
    pr.set_defaults(func=prefs)

    s = sub.add_parser("show", help="查看当前 mqtt 配置 / defaults 文件")
    s.add_argument("--devices", required=True)
    s.set_defaults(func=show)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
