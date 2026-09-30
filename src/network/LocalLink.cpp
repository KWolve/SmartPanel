/*
 * LocalLink.cpp - 本地模式互联实现（见 LocalLink.h）
 */
#include "network/LocalLink.h"

#include "network/LocalBrokerService.h"
#include "network/MiniBroker.h"
#include "network/PanelLink.h"
#include "device/RelayManager.h"
#include "scene/SceneManager.h"
#include "storage/ConfigStore.h"
#include "utils/Log.h"
#include "logic/ui_common.h"          // nowMs

#include <mqtt/mqtt_client.h>
#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <algorithm>
#include <string.h>
#include <thread>

LocalLink* LocalLink::getInstance() {
    static LocalLink s;
    return &s;
}

bool LocalLink::isMaster() const {
    return ConfigStore::getInstance()->runMode() == ConfigStore::MODE_MASTER;
}

void LocalLink::start() {
    stop();
    int mode = ConfigStore::getInstance()->runMode();
    if (mode == ConfigStore::MODE_MASTER) {
        startMaster();
    } else if (mode == ConfigStore::MODE_SLAVE) {
        startSlave();
    } else {
        LOGD("LocalLink: HA mode, broker link inactive");
    }
}

void LocalLink::stop() {
    stopSlave();
    stopMasterClient();
    mPeers.clear();
    mActive = false;
}

void LocalLink::stopMasterClient() {
    mMasterConnected = false;
    mqtt::Client* c = static_cast<mqtt::Client*>(mMasterClient);
    if (c != nullptr) {
        delete c;
        mMasterClient = nullptr;
    }
    mExtBroker = false;
}

// ── 主机 ──────────────────────────────────────────────────────

// 钟工 2026-09-30：优先「依托 zkgui 拉起板内 broker 服务」，失败才用 app 内嵌 MiniBroker
void LocalLink::startMaster() {
    if (LocalBrokerService::ensureRunning(3000)) {
        startMasterViaService();
        return;
    }
    LOGW("LocalLink: board broker service unavailable -> fallback to in-app MiniBroker");
    startMasterEmbedded();
}

// 服务路径：本机当客户端，连 zkmqtt（同一份 broker 服务同时服务从机与小程序/HA）
void LocalLink::startMasterViaService() {
    mExtBroker = true;
    mActive = true;
    PeerInfo self;
    self.id = ConfigStore::getInstance()->deviceId();
    self.name = ConfigStore::getInstance()->deviceName();
    self.ip = PanelLink::localIp();
    memset(self.relays, 0, sizeof(self.relays));
    self.lastSeenMs = nowMs();
    mPeers.push_back(self);
    std::thread([this]() { masterTick(); }).detach();
    LOGD("LocalLink: master mode via board broker service (zkmqtt :1883, started_by_app=%d)",
         LocalBrokerService::startedByUs() ? 1 : 0);
}

// 回退路径：app 内嵌 MiniBroker（QoS0，无 Will）
void LocalLink::startMasterEmbedded() {
    MiniBroker* b = MiniBroker::getInstance();
    if (!b->start(1883)) {
        LOGW("LocalLink: master broker start failed");
        return;
    }
    b->setPublishHook([this](const std::string& t, const std::string& p) {
        onBrokerPublish(t, p);
    });
    mActive = true;
    // 本机也进设备表
    PeerInfo self;
    self.id = ConfigStore::getInstance()->deviceId();
    self.name = ConfigStore::getInstance()->deviceName();
    self.ip = PanelLink::localIp();
    memset(self.relays, 0, sizeof(self.relays));
    self.lastSeenMs = nowMs();
    mPeers.push_back(self);
    publishScenesConfig();
    publishOwnStatus();
    LOGD("LocalLink: master mode up, ip=%s", self.ip.c_str());
}

void LocalLink::publishScene(const std::string& name) {
    if (!isMaster()) return;
    mLastSceneName = name;
    mLastScenePubMs = nowMs();
    if (mExtBroker) {
        mqtt::Client* c = static_cast<mqtt::Client*>(mMasterClient);
        if (c == nullptr || !mMasterConnected) {
            LOGW("LocalLink: publishScene skipped (broker service not connected)");
            return;
        }
        c->publish(SP_BCAST_SCENE, name, mqtt::QOS_AT_MOST_ONCE, false);
    } else {
        MiniBroker::getInstance()->publish(SP_BCAST_SCENE, name, false);
    }
    LOGD("LocalLink: scene broadcast '%s' (ext=%d)", name.c_str(), mExtBroker ? 1 : 0);
}

void LocalLink::publishScenesConfig() {
    if (!isMaster()) return;
    if (mExtBroker) {
        mqtt::Client* c = static_cast<mqtt::Client*>(mMasterClient);
        if (c == nullptr || !mMasterConnected) return;
        c->publish(SP_BCAST_SCENES, ConfigStore::getInstance()->sceneJson(),
                   mqtt::QOS_AT_MOST_ONCE, true);
        return;
    }
    MiniBroker::getInstance()->publish(
        SP_BCAST_SCENES, ConfigStore::getInstance()->sceneJson(), true);
}

// 主机侧收到消息（分服务路径/内嵌路径共用）：外部触发情景、外部直接控继电器、收集子设备状态
void LocalLink::onMasterMessage(const std::string& topic, const std::string& payload) {
    if (topic == SP_BCAST_SCENE) {
        // 回声抑制：自己刚广播的那条不再重复激活
        if (payload == mLastSceneName && nowMs() - mLastScenePubMs < 1500) return;
    }
    if (topic == SP_BCAST_SCENES) return;      // 情景全集由主机自己发布
    onBrokerPublish(topic, payload);
}

void LocalLink::onBrokerPublish(const std::string& topic, const std::string& payload) {
    // 外部触发情景广播（小程序/HA/其它设备）：本机执行，不再二次广播
    // （broker 已把消息转发给所有订阅者，含各从机）
    if (topic == SP_BCAST_SCENE) {
        LOGD("LocalLink: scene broadcast from external: %s", payload.c_str());
        SceneManager::getInstance()->activate(payload, true);
        return;
    }
    // 外部对本机继电器的直接控制：smartpanel/<本机ID>/switch/relay_<n>/command
    const std::string ownPrefix = std::string("smartpanel/")
                                + ConfigStore::getInstance()->deviceId() + "/switch/relay_";
    if (topic.find(ownPrefix) == 0) {
        std::string rest = topic.substr(ownPrefix.size());       // "<n>/command"
        int n = atoi(rest.c_str());
        if (n >= 1 && n <= 3 && rest.find("/command") != std::string::npos) {
            // 严格解析（钟工 2026-09-30：重连/重订阅后的 retained 回放与空 payload
            //   不得被当成 OFF 把灯关掉）
            bool on = false;
            if (payload == "ON" || payload == "1" || payload == "on")      on = true;
            else if (payload == "OFF" || payload == "0" || payload == "off") on = false;
            else {
                LOGW("LocalLink: ignore non ON/OFF relay command (%s = [%s])",
                     topic.c_str(), payload.c_str());
                return;
            }
            LOGD("LocalLink: external relay command ch=%d on=%d", n, on);
            RelayManager::getInstance()->set(n, on);
            return;
        }
    }
    // 收集 smartpanel/<id>/status
    const std::string pre = "smartpanel/";
    if (topic.find(pre) != 0) return;
    std::string rest = topic.substr(pre.size());
    if (rest.size() < 8 || rest.compare(rest.size() - 7, 7, "/status") != 0) return;
    std::string id = rest.substr(0, rest.size() - 7);
    if (id == "broadcast") return;

    rapidjson::Document d;
    if (d.Parse(payload.c_str()).HasParseError() || !d.IsObject()) return;
    std::string name = d.HasMember("name") && d["name"].IsString() ? d["name"].GetString() : "";
    std::string ip = d.HasMember("ip") && d["ip"].IsString() ? d["ip"].GetString() : "";

    for (auto& p : mPeers) {
        if (p.id == id) {
            if (!name.empty()) p.name = name;
            if (!ip.empty()) p.ip = ip;
            if (d.HasMember("relays") && d["relays"].IsArray()) {
                for (int i = 0; i < 3 && i < (int)d["relays"].Size(); ++i) {
                    p.relays[i] = d["relays"][i].GetBool();
                }
            }
            p.lastSeenMs = nowMs();
            return;
        }
    }
    PeerInfo p;
    p.id = id;
    p.name = name.empty() ? id : name;
    p.ip = ip;
    memset(p.relays, 0, sizeof(p.relays));
    if (d.HasMember("relays") && d["relays"].IsArray()) {
        for (int i = 0; i < 3 && i < (int)d["relays"].Size(); ++i) {
            p.relays[i] = d["relays"][i].GetBool();
        }
    }
    p.lastSeenMs = nowMs();
    mPeers.push_back(p);
    LOGD("LocalLink: peer online %s (%s)", id.c_str(), p.name.c_str());
}

std::vector<PeerInfo> LocalLink::peers() {
    return mPeers;
}

void LocalLink::renamePeer(const std::string& id, const std::string& name) {
    ConfigStore::getInstance()->setPeerName(id, name);
    for (auto& p : mPeers) {
        if (p.id == id) p.name = name;
    }
}

std::string LocalLink::statusText() {
    int mode = ConfigStore::getInstance()->runMode();
    if (mode == ConfigStore::MODE_MASTER) {
        int n = 0;
        for (auto& p : mPeers) {
            if (nowMs() - p.lastSeenMs < 60 * 1000) ++n;
        }
        char buf[64];
        snprintf(buf, sizeof(buf), "本地主机 在线设备 %d", n);
        return buf;
    }
    if (mode == ConfigStore::MODE_SLAVE) {
        return std::string("本地从机 ") + (mSlaveConnected ? "已连接主机" : "连接中/离线");
    }
    return "";
}

// ── 从机 ──────────────────────────────────────────────────────

std::string LocalLink::ownStatusJson() {
    rapidjson::StringBuffer sb;
    rapidjson::Writer<rapidjson::StringBuffer> w(sb);
    ConfigStore* cs = ConfigStore::getInstance();
    w.StartObject();
    w.Key("name"); w.String(cs->deviceName().c_str());
    w.Key("ip");   w.String(PanelLink::localIp().c_str());
    w.Key("relays");
    w.StartArray();
    for (int i = 1; i <= 3; ++i) w.Bool(RelayManager::getInstance()->get(i));
    w.EndArray();
    w.EndObject();
    return std::string(sb.GetString(), sb.GetSize());
}

void LocalLink::publishOwnStatus() {
    std::string p = ConfigStore::getInstance()->mqttPrefix();  // smartpanel/<id>
    if (mExtBroker) {
        // 服务路径：本机是客户端，状态/开关状态均 retained 发布
        mqtt::Client* c = static_cast<mqtt::Client*>(mMasterClient);
        if (c == nullptr || !mMasterConnected) return;
        c->publish(p + "/status", ownStatusJson(), mqtt::QOS_AT_MOST_ONCE, true);
        for (int ch = 1; ch <= 3; ++ch) {
            c->publish(p + "/switch/relay_" + std::to_string(ch) + "/state",
                       RelayManager::getInstance()->get(ch) ? "ON" : "OFF",
                       mqtt::QOS_AT_MOST_ONCE, true);
        }
        return;
    }
    MiniBroker* b = MiniBroker::getInstance();
    if (isMaster()) {
        // 主机直接写入 broker 保留表，让后来接入的从机/小程序拿到
        b->publish(p + "/status", ownStatusJson(), true);
        for (int ch = 1; ch <= 3; ++ch) {
            b->publish(p + "/switch/relay_" + std::to_string(ch) + "/state",
                       RelayManager::getInstance()->get(ch) ? "ON" : "OFF", true);
        }
        return;
    }
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    if (c == nullptr || !mSlaveConnected) return;
    c->publish(p + "/status", ownStatusJson(), mqtt::QOS_AT_MOST_ONCE, true);
    for (int ch = 1; ch <= 3; ++ch) {
        c->publish(p + "/switch/relay_" + std::to_string(ch) + "/state",
                   RelayManager::getInstance()->get(ch) ? "ON" : "OFF",
                   mqtt::QOS_AT_MOST_ONCE, true);
    }
}

void LocalLink::startSlave() {
    std::thread([this]() { slaveTick(); }).detach();
    mActive = true;
}

// 主机（服务路径）心跳：重连 + relay 变化即上报 + 周期刷新
void LocalLink::masterTick() {
    static bool lastRelays[3] = {false, false, false};
    while (mActive && ConfigStore::getInstance()->runMode() == ConfigStore::MODE_MASTER && mExtBroker) {
        if (!mMasterConnected) {
            // 服务挂了就重新拉起（zkgui 托管：不依赖 init）
            if (!LocalBrokerService::isRunning(200)) {
                LOGW("LocalLink: board broker service missing -> respawn");
                LocalBrokerService::ensureRunning(3000);
            }
            try {
                mqtt::Client::Configuration conf;
                conf.server = "127.0.0.1:1883";
                conf.client_id = "master_" + ConfigStore::getInstance()->deviceId();
                conf.username = "";
                conf.password = "";
                conf.clean_session = true;
                conf.on_connected = [this](const std::string&) {
                    mMasterConnected = true;
                    LOGD("LocalLink: master connected to board broker service");
                    mqtt::Client* c = static_cast<mqtt::Client*>(mMasterClient);
                    std::string p = ConfigStore::getInstance()->mqttPrefix();
                    c->subscribe(SP_BCAST_SCENE, mqtt::QOS_AT_MOST_ONCE,
                        [this](const std::string& t, const std::string& pl) {
                            onMasterMessage(t, pl);
                        });
                    c->subscribe("smartpanel/+/status", mqtt::QOS_AT_MOST_ONCE,
                        [this](const std::string& t, const std::string& pl) {
                            onMasterMessage(t, pl);
                        });
                    c->subscribe(p + "/switch/+/command", mqtt::QOS_AT_MOST_ONCE,
                        [this](const std::string& t, const std::string& pl) {
                            onMasterMessage(t, pl);
                        });
                    publishScenesConfig();
                    publishOwnStatus();
                };
                conf.on_disconnected = [this](const std::string&) {
                    mMasterConnected = false;
                    LOGW("LocalLink: master lost board broker service");
                };
                mqtt::Client* nc = new mqtt::Client(conf);
                mqtt::Client* old = static_cast<mqtt::Client*>(mMasterClient);
                mMasterClient = nc;
                delete old;
            } catch (const std::exception& e) {
                LOGW("LocalLink: master connect (service) failed: %s", e.what());
            } catch (...) {
                LOGW("LocalLink: master connect (service) failed");
            }
        }
        bool changed = false;
        for (int i = 0; i < 3; ++i) {
            bool v = RelayManager::getInstance()->get(i + 1);
            if (v != lastRelays[i]) {
                lastRelays[i] = v;
                changed = true;
            }
        }
        if (changed) publishOwnStatus();
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    if (!mActive) stopMasterClient();
}

void LocalLink::stopSlave() {
    mSlaveConnected = false;
    mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
    if (c != nullptr) {
        delete c;
        mClient = nullptr;
    }
}

void LocalLink::slaveTick() {
    while (mActive && ConfigStore::getInstance()->runMode() == ConfigStore::MODE_SLAVE) {
        if (!mSlaveConnected) {
            std::string ip = ConfigStore::getInstance()->masterIp();
            if (!ip.empty()) {
                try {
                    mqtt::Client::Configuration conf;
                    conf.server = ip + ":1883";
                    conf.client_id = "slave_" + ConfigStore::getInstance()->deviceId();
                    conf.username = "";
                    conf.password = "";
                    conf.clean_session = true;
                    conf.on_connected = [this](const std::string&) {
                        mSlaveConnected = true;
                        LOGD("LocalLink: slave connected to master");
                        mqtt::Client* c = static_cast<mqtt::Client*>(mClient);
                        std::string p = ConfigStore::getInstance()->mqttPrefix();
                        c->subscribe(SP_BCAST_SCENE, mqtt::QOS_AT_MOST_ONCE,
                            [this](const std::string& t, const std::string& pl) {
                                onSlaveMessage(t, pl);
                            });
                        c->subscribe(SP_BCAST_SCENES, mqtt::QOS_AT_MOST_ONCE,
                            [this](const std::string& t, const std::string& pl) {
                                onSlaveMessage(t, pl);
                            });
                        c->subscribe(p + "/switch/+/command", mqtt::QOS_AT_MOST_ONCE,
                            [this](const std::string& t, const std::string& pl) {
                                onSlaveMessage(t, pl);
                            });
                        publishOwnStatus();
                    };
                    conf.on_disconnected = [this](const std::string&) {
                        mSlaveConnected = false;
                        LOGW("LocalLink: slave disconnected");
                    };
                    mqtt::Client* nc = new mqtt::Client(conf);
                    mqtt::Client* old = static_cast<mqtt::Client*>(mClient);
                    mClient = nc;
                    delete old;
                } catch (const std::exception& e) {
                    LOGW("LocalLink: slave connect failed: %s", e.what());
                } catch (...) {
                    LOGW("LocalLink: slave connect failed");
                }
            }
        }
        // 2s 周期：状态变化上报（lastStatus 变化时）
        static bool lastRelays[3] = {false, false, false};
        bool changed = false;
        for (int i = 0; i < 3; ++i) {
            bool v = RelayManager::getInstance()->get(i + 1);
            if (v != lastRelays[i]) {
                lastRelays[i] = v;
                changed = true;
            }
        }
        if (changed) publishOwnStatus();
        std::this_thread::sleep_for(std::chrono::seconds(2));
    }
    // 退出循环（模式切换）后释放
    if (!mActive) stopSlave();
}

void LocalLink::onSlaveMessage(const std::string& topic, const std::string& payload) {
    if (topic == SP_BCAST_SCENE) {
        SceneManager::getInstance()->activate(payload, true);
        return;
    }
    if (topic == SP_BCAST_SCENES) {
        // 主机分发情景定义：本地模式直接采用（与本地 JSON 合并以主机为准）
        SceneManager::getInstance()->importScenesJson(payload, true);
        return;
    }
    std::string p = ConfigStore::getInstance()->mqttPrefix() + "/switch/relay_";
    if (topic.find(p) == 0) {
        // 只认「<n>/command」+ payload 恰为 ON/OFF（钟工 2026-09-30：原来 `payload == "ON"`
        //   把它当开关值 —— 空 payload（retained 清除）/状态回放都会被当成 OFF → 关灯）。
        std::string rest = topic.substr(p.size());
        const std::string suf = "/command";
        if (rest.size() != 1 + suf.size() || rest.compare(1, suf.size(), suf) != 0) return;
        int ch = rest[0] - '0';
        if (ch < 1 || ch > 3) return;
        if (payload == "ON") {
            RelayManager::getInstance()->set(ch, true);
        } else if (payload == "OFF") {
            RelayManager::getInstance()->set(ch, false);
        } else {
            LOGW("LocalLink: ignore non ON/OFF command (%s = [%s])", topic.c_str(), payload.c_str());
        }
    }
}
