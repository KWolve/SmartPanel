/*
 * MqttBridge.cpp - Home Assistant MQTT 标准接入实现
 *
 * 规范来源：Z20_HA_Switch 工程 doc/mqtt_protocol.md（HA MQTT Discovery，
 * 缩写字段 stat_t/cmd_t/pl_on/...，device 归组 dev 对象）。
 */

#include "network/MqttBridge.h"

#include "device/RelayManager.h"
#include "device/SensorManager.h"
#include "network/PanelLink.h"
#include "scene/SceneManager.h"
#include "storage/ConfigStore.h"
#include "utils/Log.h"

#include <mqtt/mqtt_client.h>
#include <base/json_object.h>

#include <math.h>
#include <stdio.h>
#include <thread>
#include <time.h>

MqttBridge* MqttBridge::getInstance() {
    static MqttBridge s;
    return &s;
}

namespace {

// "\u56de\u5bb6" -> UTF-8（HA 的 tojson 会把中文转义）
std::string unescapeJson(const std::string& s) {
    std::string out;
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (c != '\\' || i + 1 >= s.size()) {
            out += c;
            continue;
        }
        char n = s[++i];
        if (n == 'u' && i + 4 < s.size()) {
            unsigned cp = 0;
            for (int k = 1; k <= 4; ++k) {
                char h = s[i + k];
                unsigned v = 0;
                if (h >= '0' && h <= '9') v = h - '0';
                else if (h >= 'a' && h <= 'f') v = h - 'a' + 10;
                else if (h >= 'A' && h <= 'F') v = h - 'A' + 10;
                cp = cp * 16 + v;
            }
            i += 4;
            if (cp < 0x80) {
                out += (char)cp;
            } else if (cp < 0x800) {
                out += (char)(0xC0 | (cp >> 6));
                out += (char)(0x80 | (cp & 0x3F));
            } else {
                out += (char)(0xE0 | (cp >> 12));
                out += (char)(0x80 | ((cp >> 6) & 0x3F));
                out += (char)(0x80 | (cp & 0x3F));
            }
        } else if (n == 'n') {
            out += '\n';
        } else if (n == 't') {
            out += '\t';
        } else {
            out += n;   // \" \\ \/ 等
        }
    }
    return out;
}

// 解析 HA 情景清单 [{"id":"scene.x","name":"回家"}, ...]（紧凑、无嵌套）
void parseHaScenes(const std::string& payload,
                   std::vector<std::pair<std::string, std::string> >& out) {
    out.clear();
    size_t pos = 0;
    while (pos < payload.size()) {
        size_t idKey = payload.find("\"id\"", pos);
        if (idKey == std::string::npos) break;
        size_t colon = payload.find(':', idKey);
        if (colon == std::string::npos) break;
        size_t q1 = payload.find('"', colon);
        if (q1 == std::string::npos) break;
        size_t q2 = payload.find('"', q1 + 1);
        if (q2 == std::string::npos) break;
        std::string id = unescapeJson(payload.substr(q1 + 1, q2 - q1 - 1));

        std::string name = id;
        size_t nameKey = payload.find("\"name\"", q2);
        size_t nextId = payload.find("\"id\"", q2);
        if (nameKey != std::string::npos && (nextId == std::string::npos || nameKey < nextId)) {
            size_t nc = payload.find(':', nameKey);
            size_t n1 = (nc == std::string::npos) ? std::string::npos : payload.find('"', nc);
            size_t n2 = (n1 == std::string::npos) ? std::string::npos : payload.find('"', n1 + 1);
            if (n1 != std::string::npos && n2 != std::string::npos) {
                name = unescapeJson(payload.substr(n1 + 1, n2 - n1 - 1));
            }
        }
        if (!id.empty()) out.push_back(std::make_pair(id, name));
        pos = q2 + 1;
    }
}

}   // namespace

// ── v7.3（2026-09-28）：单调钟 + client 回收 —— 治「同 client_id 自踢」风暴 ──
static long long monoNowMs() {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0) {
        return (long long)ts.tv_sec * 1000LL + (long long)(ts.tv_nsec / 1000000L);
    }
    return (long long)time(NULL) * 1000LL;
}

// 需已持 mMtx：销毁当前 client（其析构会断开 paho 连接）；代次 +1 -> 旧 client 的迟到回调作废
void MqttBridge::dropClientLocked() {
    if (mClient != nullptr) {
        mqtt::Client* old = static_cast<mqtt::Client*>(mClient);
        mClient = nullptr;
        mClientGen++;
        delete old;
        LOGD("MqttBridge: old client dropped (gen=%d)", mClientGen);
    }
}

void MqttBridge::stop() {
    std::lock_guard<std::mutex> lk(mMtx);
    mConnected = false;
    mConnecting = false;
    dropClientLocked();
    mStarted = false;
}

std::string MqttBridge::prefix() const {
    return ConfigStore::getInstance()->mqttPrefix();
}

std::string MqttBridge::uidBase() const {
    std::string u = prefix();
    for (size_t i = 0; i < u.size(); ++i) {
        if (u[i] == '/') u[i] = '_';
    }
    return u;
}

void MqttBridge::init() {
    if (mStarted) return;
    mStarted = true;
    // P4: 仅 HA 模式启用外接 broker
    if (ConfigStore::getInstance()->runMode() != ConfigStore::MODE_HA
        || !ConfigStore::getInstance()->mqttEnabled()) {
        LOGD("MqttBridge: disabled (mode=%d)", ConfigStore::getInstance()->runMode());
        return;
    }
    mConnecting = true;
    std::thread(&MqttBridge::connect, this).detach();
}

// 看门狗：HA 模式下断线就重连（钟工 2026-09-25 验收发现：之前只在 init 连一次）
//   v7.3（2026-09-28）：**单一重连 + 节流/指数退避** —— 原来只要 !mConnected 就每秒起一个
//   connect()，而 connect() 每次 new 且不销毁旧的 -> 多个 client 同 client_id 在 broker 互踢（现场每秒 2~3 次）。
void MqttBridge::tick() {
    if (!mStarted) return;
    if (ConfigStore::getInstance()->runMode() != ConfigStore::MODE_HA
        || !ConfigStore::getInstance()->mqttEnabled()) {
        return;
    }
    const long long now = monoNowMs();
    bool connected = false, connecting = false;
    {
        std::lock_guard<std::mutex> lk(mMtx);
        connected = mConnected;
        connecting = mConnecting;
    }
    if (!connected && !connecting) {
        long long backoff = 10000;                                    // 10s 起
        for (int i = 0; i < mFailStreak && i < 3; i++) backoff *= 2;   // 10→20→40→（封顶）60s
        if (backoff > 60000) backoff = 60000;
        if (mLastTryMono != 0 && (now - mLastTryMono) < backoff) {
            return;                                                   // 退避窗口内不重试
        }
        LOGW("MqttBridge: link down -> reconnect (gen=%d fail=%d backoff=%lldms total=%d)",
             mClientGen, mFailStreak, backoff, mReconnectCount);
        {
            std::lock_guard<std::mutex> lk(mMtx);
            mConnecting = true;
        }
        std::thread(&MqttBridge::connect, this).detach();
        return;
    }
    if (!connected) return;
    // 状态上报差分兜底（1s）：触摸/情景/UDP/开机 restore 任何一条路漏报都能补齐；
    // 也是监听回调被误抹掉时的最后一道保险（钟工 2026-09-27 问题单）。
    relayWatchdog();
}

void MqttBridge::connect() {
    try {
        mqtt::Client::Configuration conf;
        conf.server = ConfigStore::getInstance()->mqttServer();
        conf.client_id = uidBase();
        conf.username = ConfigStore::getInstance()->mqttUser();
        conf.password = ConfigStore::getInstance()->mqttPassword();
        conf.clean_session = true;
        if (conf.server.empty()) {
            LOGW("MqttBridge: no server configured");
            std::lock_guard<std::mutex> lk(mMtx);
            mConnecting = false;
            return;
        }

        // LWT：断线时 broker 自动发布 offline
        conf.will.topic = prefix() + "/availability";
        conf.will.message = "offline";
        conf.will.qos = mqtt::QOS_AT_MOST_ONCE;
        conf.will.retained = true;

        // v7.3：建新 client 之前**先回收旧的**，并用代次(gen)把旧 client 的迟到回调全部作废；
        //   回调里只在锁内翻标志，onConnected() 放到锁外跑（它自己会 publish/subscribe）。
        {
            std::lock_guard<std::mutex> lk(mMtx);
            dropClientLocked();
            const int gen = ++mClientGen;
            conf.on_connected = [this, gen](const std::string&) {
                {
                    std::lock_guard<std::mutex> lk(mMtx);
                    if (gen != mClientGen) return;          // 旧 client 的迟到回调
                    mConnected = true;
                    mConnecting = false;
                    mFailStreak = 0;
                }
                LOGD("MqttBridge: connected (gen=%d)", gen);
                onConnected();
            };
            conf.on_disconnected = [this, gen](const std::string&) {
                std::lock_guard<std::mutex> lk(mMtx);
                if (gen != mClientGen) return;
                mConnected = false;
                mConnecting = false;
                if (mFailStreak < 100) mFailStreak++;
                LOGW("MqttBridge: disconnected (gen=%d fail=%d)", gen, mFailStreak);
            };
            mLastTryMono = monoNowMs();
            mReconnectCount++;
            mClient = new mqtt::Client(conf);
            LOGD("MqttBridge: connecting %s ... (gen=%d total=%d)",
                 conf.server.c_str(), gen, mReconnectCount);
        }
    } catch (const std::exception& e) {
        {
            std::lock_guard<std::mutex> lk(mMtx);
            mConnecting = false;
        }
        LOGE("MqttBridge: connect failed: %s", e.what());
    } catch (...) {
        {
            std::lock_guard<std::mutex> lk(mMtx);
            mConnecting = false;
        }
        LOGE("MqttBridge: connect failed (unknown)");
    }
}

void MqttBridge::onConnected() {
    // 继电器状态变化上报回调：**每次连接都幂等注册**（具名 key，同 key 只占一个槽）。
    // 不用旧版 mRelayListenerHooked 门闩的原因：一旦回调被任何地方抹掉，门闩会让它
    // 在这次进程生命周期内永远无法恢复（钟工 2026-09-27 实测事故）。
    RelayManager::getInstance()->addListener("mqtt_bridge",
        [this](int ch, bool on) {
            publishRelayChanged(ch, on);
        });
    LOGD("MqttBridge: relay listener ok, total listeners=%d [%s]",
         RelayManager::getInstance()->listenerCount(),
         RelayManager::getInstance()->listenerKeys().c_str());

    // 顺序：先宣告在线（HA 才不会把紧接着的 discovery 当成不可用），再 discovery/订阅，
    // 最后主动推一遍**新鲜**状态（覆盖 broker 上可能残留的旧 retained）。
    publishAvailability(true);
    publishDiscovery();
    subscribeAll();
    publishAllRelayStates();
    // 面板完整状态（relays 字段来自 RelayManager 单例，不再全 false）
    publishStatus(realStatusJson());
}

// 单一事实源：PanelLink::statusJson() 现在只读 RelayManager 单例（不再用可空注入指针）
std::string MqttBridge::realStatusJson() const {
    return PanelLink::getInstance()->statusJson();
}

void MqttBridge::subscribeAll() {
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    if (c == nullptr) return;
    std::string p = prefix();
    c->subscribe(p + "/switch/+/command", mqtt::QOS_AT_MOST_ONCE,
        [this](const std::string& topic, const std::string& payload) {
            onMessage(topic, payload);
        });
    c->subscribe(p + "/scene/+/command", mqtt::QOS_AT_MOST_ONCE,
        [this](const std::string& topic, const std::string& payload) {
            onMessage(topic, payload);
        });
    // HA 情景清单（由 HA 侧自动化发布，retained）：面板拉取展示用
    c->subscribe("smartpanel/ha/scenes", mqtt::QOS_AT_MOST_ONCE,
        [this](const std::string& topic, const std::string& payload) {
            onMessage(topic, payload);
        });
    // 当前生效情景（HA 触发后回报，retained）：面板据此高亮当前情景
    c->subscribe("smartpanel/ha/active_scene", mqtt::QOS_AT_MOST_ONCE,
        [this](const std::string& topic, const std::string& payload) {
            onMessage(topic, payload);
        });
    LOGD("MqttBridge: subscribed switch+/scene+ commands + ha/scenes + ha/active_scene");
}

void MqttBridge::onMessage(const std::string& topic, const std::string& payload) {
    LOGD("MqttBridge: recv %s = %s", topic.c_str(), payload.c_str());

    // HA 当前生效情景（retained）：只存下来，UI 每次刷新时读
    if (topic == "smartpanel/ha/active_scene") {
        mActiveHaScene = payload;
        while (!mActiveHaScene.empty() &&
               (mActiveHaScene[mActiveHaScene.size() - 1] == '\n' ||
                mActiveHaScene[mActiveHaScene.size() - 1] == '\r' ||
                mActiveHaScene[mActiveHaScene.size() - 1] == ' ')) {
            mActiveHaScene.erase(mActiveHaScene.size() - 1);
        }
        LOGD("MqttBridge: active HA scene = %s", mActiveHaScene.c_str());
        return;
    }

    // HA 情景清单（retained JSON）：面板只负责展示 + 点选后反向触发 HA
    if (topic == "smartpanel/ha/scenes") {
        parseHaScenes(payload, mHaScenes);
        mHaScenesFetched = true;
        LOGD("MqttBridge: HA scene list = %d", (int)mHaScenes.size());
        for (size_t i = 0; i < mHaScenes.size(); ++i) {
            LOGD("  ha scene[%d] %s = %s", (int)i, mHaScenes[i].first.c_str(),
                 mHaScenes[i].second.c_str());
        }
        return;
    }
    std::string p = prefix() + "/switch/relay_";
    if (topic.find(p) == 0) {
        // 钟工 2026-09-30 口径：**重新注册 HA 服务或断网重连不得修改灯光状态**。
        //   broker 在每次（重）订阅后会把该主题上的 **retained** 消息立刻回放一份，
        //   若把回放/空 payload/状态类 payload 当命令执行 —— 重连一次就关一次灯。
        //   所以只认「<n>/command 且 payload 恰为 ON/OFF」的消息，其余一律忽略。
        std::string rest = topic.substr(p.size());          // 期望 "<n>/command"
        const std::string suf = "/command";
        if (rest.size() != 1 + suf.size() || rest.compare(1, suf.size(), suf) != 0) return;
        int ch = rest[0] - '0';
        if (ch < 1 || ch > RelayManager::kChannels) return;
        if (payload == "ON") {
            RelayManager::getInstance()->set(ch, true);
        } else if (payload == "OFF") {
            RelayManager::getInstance()->set(ch, false);
        } else {
            LOGW("MqttBridge: ignore non ON/OFF command (%s = [%s])", topic.c_str(), payload.c_str());
        }
        // set() 触发 listener -> publishRelayState 回执（retained）
        return;
    }

    std::string ps = prefix() + "/scene/scene_";
    if (topic.find(ps) == 0 && payload == "ON") {
        std::string rest = topic.substr(ps.size());
        int idx = rest.empty() ? 0 : rest[0] - '0';
        std::vector<SceneDef> scenes = SceneManager::getInstance()->scenes();
        if (idx >= 1 && idx <= (int)scenes.size()) {
            SceneManager::getInstance()->activate(scenes[idx - 1].name, false);
        }
    }
}

void MqttBridge::publishAvailability(bool online) {
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    if (c == nullptr) return;
    c->publish(prefix() + "/availability", online ? "online" : "offline",
               mqtt::QOS_AT_MOST_ONCE, true);
}

void MqttBridge::publishRelayState(int ch, bool on) {
    if (!mConnected || mClient == nullptr) {
        // 显式可观测：不再静默 return（钟工 2026-09-27：以前这里默默丢掉，现场看不出问题）
        LOGW("MqttBridge: drop relay_%d state publish (connected=%d, client=%s)",
             ch, mConnected ? 1 : 0, mClient ? "set" : "null");
        return;
    }
    if (ch < 1 || ch > RelayManager::kChannels) return;
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    char topic[128];
    snprintf(topic, sizeof(topic), "%s/switch/relay_%d/state", prefix().c_str(), ch);
    c->publish(topic, on ? "ON" : "OFF", mqtt::QOS_AT_MOST_ONCE, true);
    mLastRelay[ch - 1] = on;      // 维护基线，兜底线程据此判差分
    mLastRelayValid = true;
    LOGD("MqttBridge: %s = %s", topic, on ? "ON" : "OFF");
}

// 状态变化统一出口：state 与 status 必须同时刷新，否则 HA 侧两套读数自相矛盾
void MqttBridge::publishRelayChanged(int ch, bool on) {
    publishRelayState(ch, on);
    publishStatus(realStatusJson());
}

// 1s 差分兜底：与 RelayManager 真实状态对比，不一致就补齐
void MqttBridge::relayWatchdog() {
    bool changed = false;
    for (int ch = 1; ch <= RelayManager::kChannels; ++ch) {
        bool v = RelayManager::getInstance()->get(ch);
        if (!mLastRelayValid || mLastRelay[ch - 1] != v) {
            changed = true;
            break;
        }
    }
    if (!changed) return;
    LOGW("MqttBridge: relay watchdog resync [%d,%d,%d] (listener miss / restore 未对齐)",
         RelayManager::getInstance()->get(1) ? 1 : 0,
         RelayManager::getInstance()->get(2) ? 1 : 0,
         RelayManager::getInstance()->get(3) ? 1 : 0);
    publishAllRelayStates();
    publishStatus(realStatusJson());
}

void MqttBridge::publishAllRelayStates() {
    for (int ch = 1; ch <= RelayManager::kChannels; ++ch) {
        publishRelayState(ch, RelayManager::getInstance()->get(ch));
    }
}

void MqttBridge::publishStatus(const std::string& json) {
    if (!mConnected || mClient == nullptr) return;
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    c->publish(prefix() + "/status", json, mqtt::QOS_AT_MOST_ONCE, true);
}

void MqttBridge::publishEvent(const std::string& json) {
    if (!mConnected || mClient == nullptr) return;
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    c->publish(prefix() + "/event", json, mqtt::QOS_AT_MOST_ONCE, false);
}

// ── HA MQTT Discovery ─────────────────────────────────────────

void MqttBridge::publishDiscovery() {
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    if (c == nullptr) return;

    ConfigStore* cs = ConfigStore::getInstance();
    std::string p = prefix();
    std::string uid = uidBase();

    // device 归组对象：HA 中所有实体归入同一台设备
    // 钟工 2026-09-25（问题单 09251751-7）：设备名用设置页里的「设备名称」（可在设置里改），
    // 不再固定 Z20 Smart Panel —— 否则 HA 后台分不出是哪台设备。
    base::JSONObject dev;
    dev.put("ids",  uid);
    dev.put("name", cs->deviceName());
    dev.put("mf",   "ZKSW");
    dev.put("mdl",  "Z20_SmartHomePanel");

    // 3 路灯具开关
    const char* icons[RelayManager::kChannels + 1] = {"", "mdi:lightbulb", "mdi:ceiling-light", "mdi:led-strip"};
    for (int ch = 1; ch <= RelayManager::kChannels; ++ch) {
        std::string rid = "relay_" + std::to_string(ch);
        base::JSONObject j;
        j.put("name",    cs->relayName(ch));
        j.put("uniq_id", uid + "_" + rid);
        j.put("p",       std::string("switch"));
        j.put("stat_t",  p + "/switch/" + rid + "/state");
        j.put("cmd_t",   p + "/switch/" + rid + "/command");
        j.put("pl_on",   std::string("ON"));
        j.put("pl_off",  std::string("OFF"));
        j.put("stat_on", std::string("ON"));
        j.put("stat_off",std::string("OFF"));
        j.put("avty_t",  p + "/availability");
        j.put("pl_avail",    std::string("online"));
        j.put("pl_not_avail",std::string("offline"));
        j.put("ic", icons[ch]);
        j.put("dev", dev);
        c->publish("homeassistant/switch/" + uid + "_" + rid + "/config",
                   j.toString(), mqtt::QOS_AT_MOST_ONCE, true);
    }

    // 温度 / 湿度传感器已移除（本机无传感器，P3 决策）。
    // 旧版本曾发布过 sensor discovery（retained），这里发空 retained 让 HA 自动清除残留实体。
    c->publish("homeassistant/sensor/" + uid + "_temperature/config", "",
               mqtt::QOS_AT_MOST_ONCE, true);
    c->publish("homeassistant/sensor/" + uid + "_humidity/config", "",
               mqtt::QOS_AT_MOST_ONCE, true);

    // 情景：按钟工 2026-09-25 口径，面板**不再**向 HA 发布情景按钮 discovery
    //（情景/自动化由 HA 操作，面板改为从 HA 拉取清单展示）。
    // 对旧版本已发布的 retained 按钮配置发空载荷，让 HA 自动清除残留实体。
    for (int i = 1; i <= 8; ++i) {
        std::string sid = "scene_" + std::to_string(i);
        c->publish("homeassistant/button/" + uid + "_" + sid + "/config", "",
                   mqtt::QOS_AT_MOST_ONCE, true);
    }
    LOGD("MqttBridge: HA discovery published (relays only, scene buttons cleared)");
}

void MqttBridge::triggerHaScene(const std::string& entityId) {
    if (!mConnected || mClient == nullptr || entityId.empty()) {
        LOGD("MqttBridge: triggerHaScene skipped (%s, connected=%d)",
             entityId.c_str(), mConnected ? 1 : 0);
        return;
    }
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    c->publish(prefix() + "/ha_scene/set", entityId, mqtt::QOS_AT_MOST_ONCE, false);
    LOGD("MqttBridge: trigger HA scene %s", entityId.c_str());
}

// 设备名等元数据变化后重发 discovery/status（retained -> HA 侧立即更新）
// 钟工 2026-09-25（问题单 09251751-7：设备名支持修改，改完要能让后台认得出来）
void MqttBridge::republishDiscovery() {
    if (!mConnected || mClient == nullptr) {
        LOGD("MqttBridge: republishDiscovery skipped (not connected)");
        return;
    }
    publishDiscovery();
    publishStatus(realStatusJson());
    LOGD("MqttBridge: discovery republished (device name updated)");
}
