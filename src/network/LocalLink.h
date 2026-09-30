/*
 * LocalLink.h - 本地模式互联（P4 双模式之「本地主机/本地从机」）
 *
 * 与 MqttBridge（HA 模式，外接 broker + HA discovery）互斥：
 *   runMode()==MODE_MASTER -> 先由 zkgui 拉起板内 broker 服务（zkmqtt，见 LocalBrokerService），
 *       本机以 **mqtt::Client 连 127.0.0.1:1883** 作主机；服务不可用时回退 app 内嵌 MiniBroker。
 *       订阅钩子收集子设备状态；情景激活 -> 广播主题；情景定义 -> retained 分发。
 *   runMode()==MODE_SLAVE  -> mqtt::Client 连主机 broker，上报本机状态(retained)，
 *       订阅广播主题执行联动，订阅本机前缀接收外部直接控制。
 *
 * 主题约定（沿用 smartpanel 前缀体系）：
 *   smartpanel/broadcast/scene        激活情景（payload=情景名，QoS0）
 *   smartpanel/broadcast/scenes       情景定义全集 v2（retained）
 *   smartpanel/<deviceId>/status      设备状态 JSON（retained：name/ip/relays）
 *   smartpanel/<deviceId>/switch/relay_<n>/command  外部/主机对设备继电器的命令
 *
 * 与 MqttBridge 的职责重叠（钟工 2026-09-27 收口）：
 *   两套链路由 runMode 严格互斥，HA 模式下本类 **不建连任何 broker**
 *   （start() 只打一行日志），所以 prefix/status 与 switch/relay_N/state 在
 *   同一时刻只有一个发布者，不存在两个发布者互相覆盖 retained 的情况。
 *   共同铁律：继电器状态只读 RelayManager::get()（唯一事实源），本类不自缓存/推算。
 */
#pragma once

#include <string>
#include <vector>

struct PeerInfo {
    std::string id;
    std::string name;
    std::string ip;
    bool relays[3];
    long long lastSeenMs;
};

class LocalLink {
public:
    static LocalLink* getInstance();

    // 按 ConfigStore::runMode() 启动/重建链路（模式切换后调用）
    void start();
    void stop();
    bool active() const { return mActive; }
    bool isMaster() const;

    // 主机：情景激活广播 + 情景定义 retained 分发
    void publishScene(const std::string& name);
    void publishScenesConfig();

    // 主机：已知子设备表（含本机，按名称排序由 UI 决定）
    std::vector<PeerInfo> peers();
    void renamePeer(const std::string& id, const std::string& name);

    // 状态行（设置页显示用）
    std::string statusText();

private:
    LocalLink() = default;
    void startMaster();
    void startMasterViaService();       // 板内 broker 服务（zkmqtt）路径
    void startMasterEmbedded();         // 回退：app 内嵌 MiniBroker
    void startSlave();
    void stopSlave();
    void stopMasterClient();
    void onBrokerPublish(const std::string& topic, const std::string& payload);
    void onSlaveMessage(const std::string& topic, const std::string& payload);
    void onMasterMessage(const std::string& topic, const std::string& payload);
    void publishOwnStatus();
    void slaveTick();                 // 2s：重连/状态上报
    void masterTick();                // 2s（服务路径）：重连/状态上报
    std::string ownStatusJson();

    bool mActive = false;
    bool mSlaveConnected = false;
    bool mExtBroker = false;          // true = 走板内 broker 服务（zkmqtt）
    bool mMasterConnected = false;
    void* mClient = nullptr;          // mqtt::Client（从机）
    void* mMasterClient = nullptr;    // mqtt::Client（主机走服务时）
    long long mLastScenePubMs = 0;    // 主机广播回声抑制
    std::string mLastSceneName;
    std::vector<PeerInfo> mPeers;
    long long mLastStatusMs = 0;
};

// 广播主题（LocalLink 与外部消费方共用）
#define SP_BCAST_SCENE   "smartpanel/broadcast/scene"
#define SP_BCAST_SCENES  "smartpanel/broadcast/scenes"
