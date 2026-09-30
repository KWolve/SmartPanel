#include "system/NetKeeper.h"

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
        LOGE("netkeeper: pthread_create failed");
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
