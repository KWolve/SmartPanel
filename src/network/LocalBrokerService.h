/*
 * LocalBrokerService.h - 让 zkgui 托管板内 MQTT broker 服务（zkmqtt）
 *
 * 钟工 2026-09-30 口径：**不依托 init 启动**，而是由 zkgui（本 app）在启动时拉起
 * `/mnt/sdnand/hub/bin/zkmqtt`，本地主机模式改成「连这个服务」而不是起 app 内嵌的 MiniBroker。
 *
 * 为什么：内嵌 MiniBroker 只支持 QoS0、无 Will、broker 生命周期跟 app 绑死；
 * 独立服务能带 QoS1 / Will / retained，且 app 重启不影响已连的从机与小程序的 broker 连接。
 *
 * 行为：
 *   - ensureRunning()：幂等。1883 已在监听 → 直接 true（谁起的不管）；
 *     否则 fork+setsid+execl 拉起服务，最多等 waitMs 直到端口可连。
 *   - 找不到二进制 / 起不来 → 返回 false，调用方自行回退（LocalLink 会回退 MiniBroker）。
 */
#pragma once

#include <string>

class LocalBrokerService {
public:
    // 保证板内 broker 在 1883 上可用（幂等）。true = 现在确实可用。
    static bool ensureRunning(int waitMs = 3000);
    // 1883 是否已可连接
    static bool isRunning(int timeoutMs = 300);
    // 实际使用的二进制路径（空 = 三个候选路径都没找到）
    static std::string binPath();
    // 日志路径（服务 stdout/stderr 重定向到这里）
    static const char* logPath() { return "/mnt/sdnand/hub/log/zkmqtt.log"; }
    static bool startedByUs() { return sStartedByUs; }

private:
    static bool sStartedByUs;
};
