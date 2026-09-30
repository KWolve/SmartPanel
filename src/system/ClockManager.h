/*
 * ClockManager.h -- 时钟（时区 + NTP）
 *
 * 口径（钟工 2026-09-27 22:17）：
 *   · **不依赖内网、不写死地址**：时钟源 = [**本机默认网关**（自动获取，DHCP/静态都适用）]
 *     + [**内置公网兜底列表**]，**逐个试直到成功**——谁先回答用谁，换现场/换客户不用改代码；
 *   · **ms 级校时**：v7.11（2026-09-29 钟工定方案②）**自研 SNTP**——每服务器取 N 个样本、
 *     按最小 RTT 挑、再按四时间戳算偏移 ((T2−T1)+(T3−T4))/2，settimeofday 写到微秒。
 *     不再用 ntp 2.1.1 包：反汇编 libntp.a 确认它 getTime() 全程不取本地时间（无往返补偿），
 *     实测每台系统性慢 ~0.3s 且跨校时不收敛；
 *   · 频率：上电重试到成功；成功后每 kRefreshMs（v7.6 = 10 分钟）刷新一次（钟工 2026-09-28 22:12）。
 * - init()：设北京时区 + 启动首次异步同步（不阻塞 UI）
 * - tick()：秒级心跳调用（未同步按间隔重试 / 已同步满 kRefreshMs 再刷）
 */
#ifndef _SYSTEM_CLOCK_MANAGER_H_
#define _SYSTEM_CLOCK_MANAGER_H_

#include <sys/time.h>
#include <string>
#include <vector>

class ClockManager {
public:
    static ClockManager* getInstance();

    void init();                              // 设时区 + 开机同步
    void tick(int retryIntervalMs = 30000);    // 秒级心跳调用（重试 / 周期刷新）

    // ── v7.7（钟工 2026-09-28 22:38「时间不同步」）──────────────────────
    // 组内时钟跟随：从机把**系统钟**对齐主机（消掉两台秒级/百毫秒级钟差）。
    //   offMs = 本机钟 − 主机钟（WallLink 双向测时结果，RTT/2 口径）
    //   · |off| > 400ms        → 立即步进（开机 / 大跳变，两台立刻同一时间）
    //   · 15ms < |off| ≤ 400ms → 小步收敛（每次 ≤ 20ms，不打乱日志/时间轴）
    //   · |off| ≤ 15ms         → 死区不动
    // 组内时钟健康（最近有 pong）时跳过自己的周期 NTP：**一台 NTP 源 = 主机**。
    void groupFollow(long long offMs, int rttMs);
    void setGroupHealthy(bool on) { mGroupHealthy = on; }
    bool groupHealthy() const { return mGroupHealthy; }
    long long groupOffMs() const { return mGroupOffMs; }
    int groupSteps() const { return mGroupSteps; }
    int groupSlews() const { return mGroupSlews; }

    bool synced() const { return mSynced; }
    long long lastSyncWallMs() const { return mLastOkMs; }
    std::string lastServer() const { return mLastServer; }
    std::vector<std::string> serverList() const { return mServers; }
    std::string statusText() const;
    // v7.3：上次校时时刻（本地 UTC-8 的 HH:MM:SS），空 = 还没成功过；供设置页/日志可观测
    std::string lastSyncLocalText() const;

    static std::string detectGatewayIp();                  // 读 /proc/net/route 拿默认网关
    static std::vector<std::string> buildServerList();     // 网关优先 + 公网兜底
    static std::vector<std::string> buildServerListWith(const std::string& gw);   // 用指定网关拼列表
    std::string gatewayIp() const { return mGateway; }     // 最近一次探测到的网关（设置页/日志用）
    bool hasGateway() const { return mHasGateway; }

    static const long long kRefreshMs = 10LL * 60 * 1000;       // 周期刷新间隔（v7.6：10 分钟，钟工 2026-09-28 22:12）

private:
    ClockManager() = default;
    void startAsyncSync();
    static void onSyncEnd(const std::string& server, const timeval* tv);
    static void* sntpThread(void* arg);      // v7.11：自研 SNTP 任务线程（异步，不阻塞 UI）

    bool mSynced = false;
    bool mInFlight = false;           // v7：是否已有一次校时任务在飞（防每秒重跑 + 任务堆积）
    long long mLastTryMs = 0;
    long long mLastOkMs = 0;          // 上次同步成功时刻（周期刷新基准）
    long long mBeforeMs = 0;          // 本次发起校时前的墙钟（日志 before/after 用）
    int mTryCount = 0;
    std::string mLastServer;          // 最近一次成功的源
    std::vector<std::string> mServers;
    std::string mGateway;             // 最近一次探测到的默认网关（空 = 网络还没就绪）
    bool mHasGateway = false;         // 本次列表里是否含网关（false -> 快重试）
    long long mLastLogMs = 0;         // v7.3：上次打「last ok」心跳日志的墙钟（每 10 分钟一条）
    bool mGroupHealthy = false;       // v7.7：组内时钟健康（最近有 pong）→ 跳过自己的周期 NTP
    long long mGroupOffMs = 0;        // 最近一次跟随看到的偏差（本机 − 主机）
    int mGroupSteps = 0;              // 累计步进次数
    int mGroupSlews = 0;              // 累计小步收敛次数
    long long mLastSkipLogMs = 0;     // 「跳过周期 NTP」日志节流
};

#endif // _SYSTEM_CLOCK_MANAGER_H_
