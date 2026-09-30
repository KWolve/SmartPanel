# -*- coding: utf-8 -*-
"""①新增 NetKeeper（读真实 wlan0 IP + WiFi 保活看门狗）②设置页 WiFi 行显示真实 IP（原来写死 192.0.2.108）
③屏保页（mainLogic，应用入口）启动保活。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

H = '''#ifndef SMART_PANEL_NETKEEPER_H_
#define SMART_PANEL_NETKEEPER_H_

#include <string>

/*
 * NetKeeper —— 网络状态查询 + WiFi 保活（钟工 2026-09-24：程序只要在运行就必须能联网）
 *  - localIp()：读 wlan0 的真实 IPv4（没有则空串）
 *  - start()/stop()：起/停保活看门狗线程（幂等；5s 巡一次，断网则按候选命令重连 + 退避）
 * 只做"能联网"这一件事：查 IP -> 没 IP 就重连 -> 打日志，方便远程判断。
 */
std::string NetKeeper_localIp();
bool NetKeeper_online();
void NetKeeper_start();
void NetKeeper_stop();

#endif /* SMART_PANEL_NETKEEPER_H_ */
'''

C = '''#include "system/NetKeeper.h"

#include "utils/Log.h"

#include <arpa/inet.h>
#include <net/if.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

#define NK_IFACE       "wlan0"
#define NK_POLL_SEC    5
#define NK_IP_WAIT_SEC 3

static volatile bool sRunning = false;
static bool sStarted = false;
static pthread_t sTid;
static std::string sLastIp;

std::string NetKeeper_localIp() {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return std::string();
    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, NK_IFACE, IFNAMSIZ - 1);
    std::string out;
    if (ioctl(fd, SIOCGIFADDR, &ifr) == 0) {
        struct sockaddr_in* sin = (struct sockaddr_in*)&ifr.ifr_addr;
        out = inet_ntoa(sin->sin_addr);
    }
    close(fd);
    if (out == "0.0.0.0") out.clear();
    return out;
}

bool NetKeeper_online() {
    return !NetKeeper_localIp().empty();
}

// 候选重连命令：设备 shell 很精简，逐个试，谁成功打谁
static const char* kReconnectCmds[] = {
    "wpa_cli -i wlan0 reconnect",
    "busybox wpa_cli -i wlan0 reconnect",
    "/sbin/wpa_cli -i wlan0 reconnect",
    "busybox ifconfig wlan0 down; sleep 1; busybox ifconfig wlan0 up",
    "ifconfig wlan0 down; sleep 1; ifconfig wlan0 up",
    NULL
};

static void tryReconnect() {
    for (int i = 0; kReconnectCmds[i] != NULL; i++) {
        FILE* fp = popen(kReconnectCmds[i], "r");
        if (fp == NULL) continue;
        char buf[128];
        while (fgets(buf, sizeof(buf), fp) != NULL) { /* 读干净避免僵尸 */ }
        int rc = pclose(fp);
        LOGD("netkeeper: try [%s] rc=%d", kReconnectCmds[i], rc);
        if (rc == 0) return;
    }
    LOGW("netkeeper: all reconnect commands failed");
}

static void* keepAliveLoop(void* arg) {
    (void)arg;
    int failStreak = 0;
    int backoff = NK_IP_WAIT_SEC;
    while (sRunning) {
        std::string ip = NetKeeper_localIp();
        if (ip.empty()) {
            failStreak++;
            LOGW("netkeeper: no ip on %s (fail #%d), reconnecting", NK_IFACE, failStreak);
            tryReconnect();
            sleep(backoff);
            backoff = (backoff < 15) ? backoff * 2 : 15;
            continue;
        }
        if (failStreak > 0 || ip != sLastIp) {
            LOGD("netkeeper: online ip=%s", ip.c_str());
        }
        sLastIp = ip;
        failStreak = 0;
        backoff = NK_IP_WAIT_SEC;
        sleep(NK_POLL_SEC);
    }
    return NULL;
}

void NetKeeper_start() {
    if (sStarted) return;
    sStarted = true;
    sRunning = true;
    if (pthread_create(&sTid, NULL, keepAliveLoop, NULL) != 0) {
        sStarted = false;
        sRunning = false;
        LOGE_TRACE("netkeeper: pthread_create failed");
        return;
    }
    LOGD("netkeeper started, ip=%s", NetKeeper_localIp().c_str());
}

void NetKeeper_stop() {
    if (!sStarted) return;
    sRunning = false;
    pthread_join(sTid, NULL);
    sStarted = false;
    LOGD("netkeeper stopped");
}
'''


def w(rel, text):
    p = os.path.join(ROOT, rel)
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    open(p, 'w', encoding='utf-8').write(text)
    print('written', rel, len(text), 'B')


w('src/system/NetKeeper.h', H)
w('src/system/NetKeeper.cpp', C)


def patch(rel, pairs, must=True):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if old not in t:
            print('%s MISS: %r' % (rel, old[:70]))
            if must:
                raise SystemExit(1)
            continue
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', rel)


# ② 设置页：WiFi 行显示真实 IP（原来是 json 里写死的 192.0.2.108）
patch('src/logic/settingsLogic.cc', [
    ('#include "storage/ConfigStore.h"',
     '#include "storage/ConfigStore.h"\n#include "system/NetKeeper.h"'),
    ('''static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    passRowDecorations();
    noteActivity();
}''',
     '''// WiFi 行：显示真实联网状态（读 wlan0 的 IP；不再写死地址）
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
    passRowDecorations();
    refreshWifiRow();
    noteActivity();
}'''),
    ('''static void onUI_show() {
    noteActivity();
}''',
     '''static void onUI_show() {
    refreshWifiRow();
    noteActivity();
}'''),
])

# ③ 屏保页（应用入口 main.ftu）启动 WiFi 保活：程序在跑就保活
patch('src/logic/mainLogic.cc', [
    ('#include "system/ClockManager.h"',
     '#include "system/ClockManager.h"\n#include "system/NetKeeper.h"'),
    ('''    passDecorations();
    MpTransferRuntimeCoordinator::instance().retain(kOwner, deviceName());''',
     '''    passDecorations();
    MpTransferRuntimeCoordinator::instance().retain(kOwner, deviceName());'''),
    ('''static void onUI_init() {''',
     '''static void onUI_init() {'''),
])

# 屏保页 onUI_init 里真正插入启动调用
p = os.path.join(ROOT, 'src/logic/mainLogic.cc')
t = open(p, encoding='utf-8').read()
anchor = 'static void onUI_init() {'
i = t.find(anchor)
j = t.find('\n', i)
ins = '\n    NetKeeper_start();          // 只要程序在跑就保活 WiFi（钟工 2026-09-24 口径）'
t = t[:j + 1] + ins + t[j + 1:]
open(p, 'w', encoding='utf-8').write(t)
print('patched mainLogic.cc: onUI_init 加 NetKeeper_start()')

# ④ json 默认文案去掉写死 IP（生成器 + 现有 json）
patch('ui/_gen/gen_pages.py', [('已连接 · 192.0.2.108', '已连接 · --')], must=False)
for rel in ('ui/settings.json', 'proto_render/main_flat.json'):
    p = os.path.join(ROOT, rel)
    if os.path.exists(p):
        t = open(p, encoding='utf-8').read()
        if '192.0.2.108' in t:
            open(p, 'w', encoding='utf-8').write(t.replace('192.0.2.108', '--'))
            print('patched', rel, '(写死 IP -> --)')
