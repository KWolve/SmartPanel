/*
 * MqttBridge.h
 *
 * Home Assistant MQTT 标准接入（参考 Z20_HA_Switch 工程的 HA Discovery 规范，
 * 见 _ref/Z20_HA_Switch/doc/mqtt_protocol.md）：
 *   prefix = ConfigStore::mqttPrefix()（默认 smartpanel/<deviceId>）
 *
 *   上行（设备 -> HA，均 retained）：
 *     prefix/availability                         -> online / offline（LWT 兜底）
 *     prefix/switch/relay_<1..3>/state            -> ON / OFF
 *     prefix/status                               -> 面板整体 JSON 状态
 *   下行（HA -> 设备）：
 *     prefix/switch/relay_<1..3>/command          <- ON / OFF
 *   HA Discovery（retained，连接成功时发布）：
 *     homeassistant/switch/<uid>/config           3 路灯具开关
 *   情景（钟工 2026-09-25 口径：情景/自动化由 HA 操作）：
 *     - 面板**不再**发布情景按钮 discovery（旧 retained 按钮配置发空载荷清除）
 *     - 面板**从 HA 拉取**情景清单：订阅 smartpanel/ha/scenes（retained JSON
 *       [{"id":"scene.x","name":"回家"}, ...]，由 HA 侧自动化发布）
 *     - 面板点情景 -> 发布 prefix/ha_scene/set = <entity_id> -> HA 自动化 scene.turn_on
 *
 * 注：本机无温湿度传感器，不上报 sensor（P3 决策）。
 * 凭据/服务器：ConfigStore（**无内置默认值**，钟工 2026-09-30）。
 *   开源版不再写死任何内网地址/账号；用户在面板「运行模式 -> HA」页扫二维码，
 *   用手机打开板内网页（WebConfigServer，:8080）填服务器地址与令牌。
 *
 * ── 职责边界（钟工 2026-09-27，消掉与 LocalLink 的重叠）────────────────
 * 两套链路由 runMode 严格互斥，同一时刻只有一方持有 broker 连接：
 *   模式 MODE_HA    -> 本类工作（外接 broker），LocalLink 不连 broker（只记日志）
 *   模式 MASTER/SLAVE -> LocalLink 工作（自带 MiniBroker/从机），本类被 stop()
 * 因此 prefix/status、prefix/switch/relay_N/state 同一时刻只有一个发布者。
 * 共同铁律：**状态一律以 RelayManager 为唯一事实源**（永远是 RelayManager::get()），
 * 任何一侧都不得自己缓存/推算继电器状态，也不得用可空指针兜底成 false。
 */
#pragma once

#include <mutex>
#include <string>
#include <utility>
#include <vector>

class MqttBridge {
public:
    static MqttBridge* getInstance();

    void init();
    void stop();
    void tick();      // 看门狗：未连接且未在连 -> 重连（由主页 1s 心跳调用）   // P4: 模式切换时断开外接 broker

    // 继电器状态变化 -> HA state（retained）；本地/触摸/情景/HA 命令统一触发
    // （由 onConnected() 向 RelayManager 注册具名监听 "mqtt_bridge"）
    void publishRelayState(int ch, bool on);
    // 面板整体 JSON 状态（与 UDP 广播同源，供需要完整状态的消费方订阅）
    void publishStatus(const std::string& json);
    void publishEvent(const std::string& json);

    // ── HA 情景（面板拉取展示 + 可触发）──
    int haSceneCount() const { return (int)mHaScenes.size(); }
    std::string haSceneId(int i) const {
        return (i >= 0 && i < (int)mHaScenes.size()) ? mHaScenes[i].first : std::string();
    }
    std::string haSceneName(int i) const {
        return (i >= 0 && i < (int)mHaScenes.size()) ? mHaScenes[i].second : std::string();
    }
    // 面板点情景 -> prefix/ha_scene/set = entityId（HA 侧自动化执行 scene.turn_on）
    void triggerHaScene(const std::string& entityId);
    bool hasFetchedHaScenes() const { return mHaScenesFetched; }
    // HA 当前生效情景（由 HA 侧回报，供主页 chip 高亮）
    std::string activeHaScene() const { return mActiveHaScene; }
    // 设备名等元数据变化后重发 discovery/status（HA 侧立即更新设备名）
    void republishDiscovery();

    bool connected() const { return mConnected; }

private:
    MqttBridge() = default;
    void connect();
    void dropClientLocked();      // 需已持 mMtx：销毁当前 client（代次 +1，旧回调作废）
    void onMessage(const std::string& topic, const std::string& payload);
    void onConnected();
    void publishAvailability(bool online);
    void publishDiscovery();      // HA MQTT Discovery（灯/情景按钮）
    void publishAllRelayStates();
    void subscribeAll();
    // 状态变化统一出口：先发 switch/relay_N/state，再刷 prefix/status，保证两者永远一致
    void publishRelayChanged(int ch, bool on);
    // 1s 差分兜底：任何来源（触摸/情景/UDP/开机 restore）漏报时补齐并告警
    void relayWatchdog();
    // 真实状态 JSON（单一事实源 = RelayManager，经 PanelLink::statusJson 生成）
    std::string realStatusJson() const;

    std::string prefix() const;   // 主题前缀
    std::string uidBase() const;  // unique_id 基（'/'->'_'）

    void* mClient = nullptr;   // mqtt::Client（延迟包含，异常安全）
    bool mConnected = false;
    bool mConnecting = false;            // 正在建连（防重复起线程）
    bool mStarted = false;
    // ── v7.3（2026-09-28）：**单一重连 + 回收旧 client**（治「同 client_id 自踢」风暴）──
    //   原实现：库自带自动重连 + 本类看门狗各一套，且 connect() 每次 new 不销毁旧的
    //   -> 多个 client 用同一 client_id 在 broker 上互踢，每秒 2~3 次 connect/disconnect，
    //      HA 实体反复掉线。现在：① 建新 client 前先 delete 旧的；② 用代次(gen)作废旧回调；
    //      ③ 重连节流 + 指数退避（10s→20s→40s→60s）。
    std::mutex mMtx;                     // 保护 mClient/mClientGen/mConnected/mConnecting
    int  mClientGen = 0;                 // 代次：旧 client 的迟到回调一律丢弃
    long long mLastTryMono = 0;          // 上次发起连接（单调钟 ms）
    int  mFailStreak = 0;                // 连续失败次数（退避用）
    int  mReconnectCount = 0;            // 累计重连次数（诊断）
    // 已发布的继电器状态（差分兜底用；mLastRelayValid=false 表示尚未建立基线）
    bool mLastRelay[3] = { false, false, false };
    bool mLastRelayValid = false;
    // HA 情景清单（entityId, 显示名），来自 smartpanel/ha/scenes（retained）
    std::vector<std::pair<std::string, std::string> > mHaScenes;
    bool mHaScenesFetched = false;
    std::string mActiveHaScene;      // 当前生效的 HA 情景 entity_id
};
