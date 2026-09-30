# -*- coding: utf-8 -*-
"""NetKeeper 接线（按真实锚点）：设置页 WiFi 行显示真实 IP + 屏保页启动保活 + 去掉 json 里写死的 IP。"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if old not in t:
            print('MISS %s: %r' % (rel, old[:60]))
            continue
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', rel)


# ① 设置页：include + 真实 IP 刷新
patch('src/logic/settingsLogic.cc', [
    ('#include "utils/Log.h"', '#include "utils/Log.h"\n#include "system/NetKeeper.h"'),
    ('''static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    passRowDecorations();
    noteActivity();
}''',
     '''// WiFi 行：显示真实联网状态（读 wlan0 的 IP；原来 json 里写死了 192.0.2.108）
static void refreshWifiRow() {
    if (mButtonRowWifiValuePtr == NULL) return;
    std::string ip = NetKeeper_localIp();
    std::string txt = ip.empty() ? std::string("未连接") : (std::string("已连接 · ") + ip);
    mButtonRowWifiValuePtr->setText(txt.c_str());
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    refreshWifiRow();
    passRowDecorations();
    noteActivity();
}'''),
    ('static void onUI_show() {\n    noteActivity();',
     'static void onUI_show() {\n    refreshWifiRow();\n    noteActivity();'),
])

# ② 屏保页（应用入口）：启动 WiFi 保活
patch('src/logic/mainLogic.cc', [
    ('#include "system/ClockManager.h"',
     '#include "system/ClockManager.h"\n#include "system/NetKeeper.h"'),
    ('''static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD''',
     '''static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    NetKeeper_start();          // 只要程序在跑就保活 WiFi（钟工 2026-09-24 口径）'''),
])

# ③ json 里的写死 IP -> 占位（生成器 + 已生成产物）
patch('ui/_gen/gen_pages.py', [('已连接 · 192.0.2.108', '已连接 · --')])
patch('ui/settings.json', [('已连接 · 192.0.2.108', '已连接 · --')], )
patch('ui/settings.json', [('192.0.2.108', '--')], )
p = os.path.join(ROOT, 'proto_render/main_flat.json')
if os.path.exists(p):
    t = open(p, encoding='utf-8').read().replace('192.0.2.108', '--')
    open(p, 'w', encoding='utf-8').write(t)
    print('patched proto_render/main_flat.json')
