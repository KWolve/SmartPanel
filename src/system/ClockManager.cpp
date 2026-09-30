/*
 * ClockManager.cpp -- 时区 + NTP（网关自动发现 + 公网兜底 + ms 级 + 周期刷新）
 *
 * 为什么这么改（钟工 2026-09-27）：
 *   1) 原来锁在 ntp **0.1.0**：回调是 `struct tm`（秒级），库内 TimeHelper::setDateTime(tm*) 只写整秒
 *      -> 每台每次校时都带 0~1s 随机误差（实测 108 慢 0.64s、71 慢 1.06s，互差 0.42s ≈ 10 帧）。
 *      新包 **2.1.1** 提供 `getTime()->timeval` / `startSyncTime(cb(timeval*))`，库内 settimeofday 写到微秒。
 *   2) 时钟源**不能写死内网地址**：先试**默认网关**（/proc/net/route，DHCP 或静态都体现在这里），
 *      网关没有 NTP 就落到**内置公网兜底列表**（国内可用为主 + 国际兜底），逐个试直到成功。
 *      实测：H3C 网关不提供 NTP（UDP 123 超时）；阿里 203.107.6.88 / 120.25.115.20 / 182.92.12.11 稳定；
 *      Cloudflare 162.159.200.1 时通时不通；Google/NIST/Apple 在国内不可达 -> 顺序如上。
 *   3) 频率：上电重试到成功；成功后每 10 分钟刷新一次（v7.6，钟工 2026-09-28 22:12）（原来只在"每天一次"，外网断过当天就不管了）。
 */
#include "system/ClockManager.h"

#include "utils/Log.h"
#include "utils/TimeHelper.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
// v7.11（2026-09-29 钟工选方案②）：**不再用 ntp 2.1.1 包**，自研 SNTP。
//   反汇编 libntp.a（只有 .a 没源码）确认：ntp::getTime() 的调用序列里
//   sendTo/receiveFrom 之间**完全没有取本地时间**（无 gettimeofday/currentTime），
//   即没有标准四时间戳偏移 ((T2−T1)+(T3−T4))/2、也不做任何往返补偿
//   -> 实测每台系统性慢 ~0.3s，且跨 10 分钟校时不收敛（校时前 −296ms / 校时后 −305ms）。
//   现在自己发 SNTP：每服务器 N 个样本、按**最小 RTT** 选、四时间戳算偏移。
#include <unistd.h>
#include <pthread.h>
// v7.13（钟工 2026-09-29「方案B」）：SNTP 客户端**用 lib-ntp 包的代码**（ntp::getTime），
//   并在外层补齐它缺的那一步——每服务器 4 个样本、按**交换耗时最小**挑一个再落钟。
//   （它源码里 getTime 是"单发一次、无往返筛选"，WiFi 唤醒慢包会把 (去程−回程)/2 的
//     不对称误差原样写进钟里，实测老包每次都落慢 ~0.3s；补了采样后落到 ±几 ms。）
#include "ntp/ntp.h"

// ── 本机墙钟（毫秒；与 WallLink::wallNowMs 同口径，但不反向依赖 wall 模块）──
static long long cmNowMs() {
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) == 0) {
        long long ms = (long long)ts.tv_sec * 1000LL + (long long)(ts.tv_nsec / 1000000L);
        if (ms > 1000000000000LL) return ms;
    }
    long long t = TimeHelper::getCurrentTime();
    if (t > 1000000000000LL) return t;
    struct tm* tm = TimeHelper::getDateTime();
    if (tm != NULL) {
        tm->tm_isdst = -1;
        time_t sec = mktime(tm);
        if (sec > 1000000000LL) return (long long)sec * 1000LL;
    }
    return t;
}

// ── v7.13 包版 SNTP 采样（钟工 2026-09-29「方案B」）─────────────────────────
//   客户端 = lib-ntp 包里的 ntp::getTime(ip, timeout)：它自己发 SNTP 包、收包、算
//   offset（源码里 target = 本机收包时刻 + offset，公式等价于标准四时间戳）。
//   我们在外面补两件事（它源码缺的）：
//     ① **多采样**：每服务器 4 次，按"交换耗时最小"挑一个 —— 滤掉 WiFi 唤醒/拥塞的慢包；
//     ② **落钟**：用挑中的样本换算成本机钟要加的量，settimeofday 一次性拨正。
//   交换耗时 = 调用 getTime 前后的墙钟差（≈ 该次往返 + 包内处理），越小越可信。
static bool pkgSample(const std::string& ip, long long* offMs, int* exchMs) {
    const long long t0 = cmNowMs();
    struct timeval tv;
    struct timeval zero;
    memset(&zero, 0, sizeof(zero));
    tv = zero;
    try {
        tv = ntp::getTime(ip, 1000);           // 包代码：单次 SNTP 交换（失败抛异常）
    } catch (std::exception& e) {
        LOGW("ClockManager: ntp::getTime(%s) fail: %s", ip.c_str(), e.what());
        return false;
    } catch (...) {
        LOGW("ClockManager: ntp::getTime(%s) fail: unknown", ip.c_str());
        return false;
    }
    const long long t1 = cmNowMs();
    if (tv.tv_sec < 1748510332) return false;  // 与包内一致的有效性门槛
    const long long tvMs = (long long)tv.tv_sec * 1000LL + (long long)(tv.tv_usec / 1000);
    *offMs = tvMs - t1;                        // >0 = 本机钟慢，需要往后拨
    *exchMs = (int)(t1 - t0);
    return true;
}

// 一个服务器取 n 个样本，按交换耗时最小挑
static bool pkgQuery(const std::string& ip, int n, long long* offMs, int* exchMs, int* gotN) {
    bool ok = false;
    long long bestOff = 0;
    int bestExch = 1 << 30;
    int cnt = 0;
    for (int i = 0; i < n; i++) {
        long long o = 0;
        int e = 0;
        if (pkgSample(ip, &o, &e)) {
            cnt++;
            if (e < bestExch) { bestExch = e; bestOff = o; ok = true; }
        }
        if (i + 1 < n) usleep(60 * 1000);
    }
    if (ok) { *offMs = bestOff; *exchMs = bestExch; }
    if (gotN != NULL) *gotN = cnt;
    return ok;
}

// ── 公网兜底（IP 直连；SNTP 按 IP 查询，不走 DNS）──
//    顺序 = 现场实测（2026-09-27，深圳/办公网）：国内三家稳定 → 国际兜底（能出网的环境才用得上）
static const char* kFallbackServers[] = {
    "203.107.6.88",     // ntp.aliyun.com      stratum2，RTT ~40ms，稳定
    "120.25.115.20",    // ntp1.aliyun.com     stratum2，RTT ~6ms，最稳
    "182.92.12.11",     // 阿里云北京           stratum2，RTT ~40ms
    "162.159.200.1",    // Cloudflare          国际兜底（实测时通时不通）
    "162.159.200.123",  // Cloudflare          国际兜底
    "216.239.35.0",     // Google              国际兜底（国内不可达，出国环境可用）
};

ClockManager* ClockManager::getInstance() {
    static ClockManager s;
    return &s;
}

/**
 * 读 /proc/net/route 拿默认网关（Destination = 00000000 的那条）。
 * 静态 IP / DHCP 都会在默认路由里体现 -> 通用，不写死地址。
 * 例：`wlan0  00000000  0101A8C0  0003 ...` -> 网关 192.0.2.1
 */
std::string ClockManager::detectGatewayIp() {
    FILE* f = fopen("/proc/net/route", "r");
    if (f == NULL) return std::string();
    char line[256];
    std::string gw;
    if (fgets(line, sizeof(line), f) == NULL) {   // 表头
        fclose(f);
        return gw;
    }
    while (fgets(line, sizeof(line), f) != NULL) {
        char iface[32] = {0};
        unsigned long dest = 0, gateway = 0, flags = 0;
        if (sscanf(line, "%31s %lx %lx %lx", iface, &dest, &gateway, &flags) != 4) continue;
        if (dest != 0UL) continue;                 // 只看默认路由
        if (gateway == 0UL) continue;
        // /proc/net/route 里是小端字节序的十六进制串（0101A8C0 表示 192.0.2.1）
        char b[32];
        snprintf(b, sizeof(b), "%lu.%lu.%lu.%lu",
                 gateway & 0xffUL, (gateway >> 8) & 0xffUL,
                 (gateway >> 16) & 0xffUL, (gateway >> 24) & 0xffUL);
        gw = b;
        break;
    }
    fclose(f);
    return gw;
}

std::vector<std::string> ClockManager::buildServerList() {
    return buildServerListWith(detectGatewayIp());
}

std::vector<std::string> ClockManager::buildServerListWith(const std::string& gw) {
    std::vector<std::string> v;
    // v7.10（钟工 2026-09-29「干掉网关」）：网关**不再**进 NTP 列表。
    //   实测 192.0.2.1 不跑 NTP（从 PC 打 123 端口 2s 超时）：每次校时先白等 ~3s
    //   才回落公网服务器（日志里的 delta≈3.3s 就是这段等待，不是拨钟量）。
    //   局域网上百台设备，没必要天天敲网关的 123 端口。形参保留只为兼容调用点。
    (void)gw;
    for (unsigned i = 0; i < sizeof(kFallbackServers) / sizeof(kFallbackServers[0]); i++) {
        const char* s = kFallbackServers[i];
        bool dup = false;
        for (size_t k = 0; k < v.size(); k++) if (v[k] == s) dup = true;
        if (!dup) v.push_back(s);                              // ② 公网兜底（逐个试）
    }
    return v;
}

static std::string joinList(const std::vector<std::string>& v) {
    std::string s;
    for (size_t i = 0; i < v.size(); i++) {
        if (i) s += ",";
        s += v[i];
    }
    return s;
}

void ClockManager::init() {
    setenv("TZ", "UTC-8", 1);     // POSIX 时区符号相反：UTC-8 = 北京时间 UTC+8
    tzset();
    const char* tz = getenv("TZ");
    LOGI("ClockManager: init TZ=%s (boot NTP sync)", tz ? tz : "(null)");
    startAsyncSync();
}

void ClockManager::startAsyncSync() {
    // v6.1（2026-09-27 22:2x 冷启动实测修正）：**每次发起校时都重新探测网关**——
    //   app 起得比网络早（实测开机 4.2s 时 `netkeeper: no ip on wlan0`，/proc/net/route 里
    //   还没有默认路由）-> 只在 init 探一次的话 gateway 永远是空，“网关优先”等于摆设。
    //   重新探测后，网络就绪后的重试就会把网关排到第一位。
    mGateway = detectGatewayIp();
    mHasGateway = !mGateway.empty() && mGateway != "0.0.0.0";
    mServers = buildServerListWith(mGateway);
    mLastTryMs = cmNowMs();
    mBeforeMs = mLastTryMs;
    mTryCount++;
    LOGI("ClockManager: ntp try %d servers[%d]=%s (gateway=%s)",
         mTryCount, (int)mServers.size(), joinList(mServers).c_str(),
         mHasGateway ? mGateway.c_str() : "(none/网络未就绪)");
    // v7.11：起自研 SNTP 线程（原来是 ntp::startSyncTime 的内部线程）
    mInFlight = true;                           // v7：标记在飞，tick() 不再每秒重跑
    pthread_t th;
    if (pthread_create(&th, NULL, sntpThread, NULL) != 0) {
        LOGW("ClockManager: sntp thread create failed (will retry)");
        mInFlight = false;                      // 没起来 -> 允许下一次重试
    } else {
        pthread_detach(th);
        LOGD("ClockManager: sntp task started (try %d, %d servers, before=%lldms)",
             mTryCount, (int)mServers.size(), mBeforeMs);
    }
}

// v7.11：自研 SNTP 任务线程（逐个服务器试；每个取 4 样本按最小 RTT 挑）
void* ClockManager::sntpThread(void* arg) {
    (void)arg;
    ClockManager* self = ClockManager::getInstance();
    const std::vector<std::string> servers = self->mServers;    // 拷一份，避免与主线程并发
    const int kSamples = 4;
    for (size_t i = 0; i < servers.size(); i++) {
        long long off = 0;
        int exch = 0, got = 0;
        if (!pkgQuery(servers[i], kSamples, &off, &exch, &got)) {
            LOGW("ClockManager: pkg ntp %s no reply (n=%d/%d)", servers[i].c_str(), got, kSamples);
            continue;
        }
        LOGI("ClockManager: pkg ntp %s exch=%dms off=%+lldms (best of %d samples)",
             servers[i].c_str(), exch, off, got);
        const long long target = cmNowMs() + off;
        if (off >= -20 && off <= 20) {
            // 已在测量噪声量级内 -> 不拨钟（避免每 10 分钟微拨一次扰动时间轴）
            LOGI("ClockManager: sntp offset in ±20ms -> keep clock");
        } else {
            struct timeval tv;
            tv.tv_sec = (time_t)(target / 1000);
            tv.tv_usec = (suseconds_t)((target % 1000) * 1000);
            if (settimeofday(&tv, NULL) != 0) {
                LOGW("ClockManager: settimeofday failed errno=%d", errno);
            } else {
                LOGI("ClockManager: clock stepped %+lldms (sntp steer, before=%lld)", off, cmNowMs() - off);
            }
        }
        struct timeval outTv;
        outTv.tv_sec = (time_t)(target / 1000);
        outTv.tv_usec = (suseconds_t)((target % 1000) * 1000);
        ClockManager::onSyncEnd(servers[i], &outTv);    // 保持既有日志口径（synced via ... before/after/delta）
        return NULL;
    }
    ClockManager::onSyncEnd(std::string(), NULL);       // 全军覆没
    return NULL;
}

void ClockManager::onSyncEnd(const std::string& server, const timeval* tv) {
    ClockManager* self = ClockManager::getInstance();
    self->mInFlight = false;                    // v7：本次任务结束（不论成败），允许下一次发起
    const long long after = cmNowMs();
    if (tv != NULL) {
        self->mSynced = true;
        self->mLastOkMs = after;
        self->mLastServer = server;
        // before/after 差 = 本次校时把本机钟拨动了多少（现场一眼能看出时区/整秒问题）
        LOGI("ClockManager: synced via %s tv=%lld.%06lds try=%d before=%lld after=%lld delta=%lldms TZ=%s",
             server.c_str(), (long long)tv->tv_sec, (long)tv->tv_usec, self->mTryCount,
             self->mBeforeMs, after, after - self->mBeforeMs, getenv("TZ") ? getenv("TZ") : "(null)");
    } else {
        LOGW("ClockManager: sync with %s failed (try %d)", server.c_str(), self->mTryCount);
    }
}


// ── v7.7（钟工 2026-09-28 22:38）：组内时钟跟随（从机系统钟对齐主机）──────
// 为什么不再让每台各自 NTP 硬校：单次 NTP 在 WiFi 上有几十~百毫秒不对称误差（实测两台差 30~180ms），
// 两台各自校时必然对不齐；组内用双向测时（RTT/2）拿到的是**两台之间**的真实偏差，据此把从机钟拉过去，
// 组内只保留**一台** NTP 源（主机），从机跟随 —— 这样两台任意时刻都同一时间，且不会互相打架。
void ClockManager::groupFollow(long long offMs, int rttMs) {
    mGroupOffMs = offMs;
    if (offMs > -15 && offMs < 15) return;                 // 死区：±15ms 内不动（测量噪声也是这个量级）
    struct timeval tv;
    if (gettimeofday(&tv, NULL) != 0) return;
    const long long nowMs = (long long)tv.tv_sec * 1000LL + tv.tv_usec / 1000LL;
    long long adj;
    bool step;
    if (offMs > 1000 || offMs < -1000) {                   // 开机/大跳变：直接步进（立刻同一时间）
        adj = -offMs;
        step = true;
    } else {                                               // 小偏差：恒定 1ms/s 慢爬
        // v7.9：WiFi 上 pingpong 的 RTT 抖动 50~130ms，任何"按比例"的增益都会把噪声当误差追
        //       （实测 1/4、1/8 都在 ±130ms 之间来回振荡）。改成**恒定速率**：方向对了就慢慢爬，
        //       100ms 偏差约 100s 收敛；对测量噪声免疫，不会来回拨钟。
        adj = (offMs > 0) ? -1 : 1;
        step = false;
    }
    if (adj == 0) return;
    const long long target = nowMs + adj;
    tv.tv_sec = (time_t)(target / 1000);
    tv.tv_usec = (suseconds_t)((target % 1000) * 1000);
    if (settimeofday(&tv, NULL) != 0) {
        LOGW("ClockManager: group align failed (off=%lldms adj=%lldms errno=%d)", offMs, adj, errno);
        return;
    }
    if (step) mGroupSteps++; else mGroupSlews++;
    LOGI("ClockManager: group %s off=%lldms adj=%lldms rtt=%dms -> now=%lld (steps=%d slews=%d)",
         step ? "STEP" : "SLEW", offMs, adj, rttMs, target, mGroupSteps, mGroupSlews);
}

void ClockManager::tick(int retryIntervalMs) {
    long long now = cmNowMs();
    // v7.3：可观测性 —— 每 10 分钟打一条「上次校时」心悸（以前只有状态文案，没有时间戳，现场只能反推）
    if (now - mLastLogMs >= 600000) {
        mLastLogMs = now;
        const std::string lt = lastSyncLocalText();
        if (mSynced && !lt.empty()) {
            LOGI("ClockManager: last ok %s (ago=%llds) src=%s next=%lldmin", lt.c_str(),
                 (now - mLastOkMs) / 1000, mLastServer.c_str(),
                 (long long)(kRefreshMs / 60000));
        } else {
            LOGI("ClockManager: last ok (none yet) synced=%d try=%d", mSynced ? 1 : 0, mTryCount);
        }
    }
    // v7（2026-09-28 现场）：**在飞保护 + 最小发起间隔**。
    //   旧逻辑只有「距上次成功 ≥ kRefreshMs 就发起」，一旦上一次成功已经过去 >30min 而后续同步又一直
    //   失败/超时，就会**每秒发起一个新任务**（现场日志：periodic NTP refresh 每秒一条，try 86→89 不停）
    //   —— 多个任务陆续完成 -> 多次 setSystemTime 用各自的旧时间把钟来回拨动（实测主机 err 103/352/310ms，
    //   两机 raw 钟一度差 ~0.9s）。现在：有任务在飞就不重复发起（20s 超时兜底），且两次发起至少间隔 30s。
    // v7.7：组内时钟健康（从机跟着主机）→ 跳过自己的周期 NTP，避免两台 NTP 互相打架
    if (mGroupHealthy) {
        if (now - mLastSkipLogMs >= 300000) {
            mLastSkipLogMs = now;
            LOGI("ClockManager: group clock healthy (off=%lldms) -> skip own NTP (group master is the time source)",
                 mGroupOffMs);
        }
        return;
    }
    if (mInFlight && (now - mLastTryMs) < 20000) return;
    if (now - mLastTryMs < 30000) return;       // 硬性最小间隔（不是每秒重跑）
    if (!mSynced) {
        // 冷启动时网络还没就绪（拿不到网关）-> 用 5s 快重试，网络一通就能校上；
        // 拿到网关后回到常规 30s 间隔（避免频繁打 NTP）。
        const int iv = mHasGateway ? retryIntervalMs : 5000;
        if (now - mLastTryMs >= iv) {
            LOGD("ClockManager: retry NTP (try %d, %s)", mTryCount + 1,
                 mHasGateway ? "有网关" : "网络未就绪->快重试");
            startAsyncSync();
        }
        return;
    }
    if (now - mLastOkMs >= kRefreshMs) {
        LOGD("ClockManager: periodic NTP refresh (%lldms since last ok)", now - mLastOkMs);
        startAsyncSync();
    }
}

std::string ClockManager::lastSyncLocalText() const {
    // 本地时间 = UTC-8（POSIX TZ 符号相反）；不依赖 setenv，自己算
    if (mLastOkMs <= 0) return std::string();
    time_t sec = (time_t)((mLastOkMs + 8LL * 3600 * 1000) / 1000);
    struct tm tmv;
    if (gmtime_r(&sec, &tmv) == NULL) return std::string();
    char b[32];
    snprintf(b, sizeof(b), "%02d:%02d:%02d", tmv.tm_hour, tmv.tm_min, tmv.tm_sec);
    return std::string(b);
}

std::string ClockManager::statusText() const {
    char buf[128];
    if (mSynced) {
        const std::string lt = lastSyncLocalText();
        if (!lt.empty()) {
            // v7.6：周期文案改回分钟显示（10 分钟刷新，钟工 2026-09-28 22:12）
            snprintf(buf, sizeof(buf), "时钟：NTP 已同步（%s，上次 %s，每 %lld 分钟刷新）",
                     mLastServer.empty() ? "-" : mLastServer.c_str(), lt.c_str(),
                     (long long)(kRefreshMs / 60000));
        } else {
            snprintf(buf, sizeof(buf), "时钟：NTP 已同步（%s，每 %lld 分钟刷新）",
                     mLastServer.empty() ? "-" : mLastServer.c_str(),
                     (long long)(kRefreshMs / 60000));
        }
    } else {
        snprintf(buf, sizeof(buf), "时钟：等待 NTP 同步（第 %d 次尝试）", mTryCount);
    }
    return std::string(buf);
}
