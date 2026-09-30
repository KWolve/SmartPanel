#include "scene/SceneManager.h"

#include "device/RelayManager.h"
#include "network/PanelLink.h"
#include "network/LocalLink.h"
#include "storage/ConfigStore.h"
#include "utils/Log.h"

#include <rapidjson/document.h>
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <string.h>

SceneManager* SceneManager::getInstance() {
    static SceneManager s;
    return &s;
}

void SceneManager::init() {
    load();
    if (mScenes.empty()) {
        // 出厂默认情景
        bool home[3]   = {true, true, false};
        bool away[3]   = {false, false, false};
        bool sleep[3]  = {false, false, true};
        bool relax[3]  = {false, true, false};
        defineScene("home", home, "回家模式: 客厅灯+灯带开");
        defineScene("away", away, "离家模式: 全部关闭, 安防联动");
        defineScene("sleep", sleep, "睡眠模式: 仅氛围灯开");
        defineScene("relax", relax, "休闲模式: 仅灯带开");
    }
}

void SceneManager::load() {
    mScenes.clear();
    std::string json = ConfigStore::getInstance()->sceneJson();
    if (json.empty()) return;

    rapidjson::Document doc;
    if (doc.Parse(json.c_str()).HasParseError() || !doc.IsObject()) return;

    for (auto it = doc.MemberBegin(); it != doc.MemberEnd(); ++it) {
        if (!it->value.IsObject()) continue;
        SceneDef def;
        def.name = it->name.GetString();
        if (it->value.HasMember("desc") && it->value["desc"].IsString()) {
            def.desc = it->value["desc"].GetString();
        }
        memset(def.relays, 0, sizeof(def.relays));
        if (it->value.HasMember("relays") && it->value["relays"].IsArray()) {
            auto& arr = it->value["relays"];
            for (rapidjson::SizeType i = 0; i < arr.Size() && i < 3; ++i) {
                if (arr[i].IsBool()) def.relays[i] = arr[i].GetBool();
            }
        }
        // P4 v2: per-device states
        if (it->value.HasMember("devs") && it->value["devs"].IsObject()) {
            for (auto d = it->value["devs"].MemberBegin(); d != it->value["devs"].MemberEnd(); ++d) {
                if (!d->value.IsArray()) continue;
                std::vector<bool> st;
                for (rapidjson::SizeType i = 0; i < d->value.Size() && i < 3; ++i) {
                    st.push_back(d->value[i].IsBool() ? d->value[i].GetBool() : false);
                }
                while (st.size() < 3) st.push_back(false);
                def.devs[d->name.GetString()] = st;
            }
        }
        mScenes.push_back(def);
    }
}

void SceneManager::save() {
    rapidjson::StringBuffer sb;
    rapidjson::Writer<rapidjson::StringBuffer> w(sb);
    w.StartObject();
    for (const auto& def : mScenes) {
        w.Key(def.name.c_str());
        w.StartObject();
        w.Key("relays");
        w.StartArray();
        for (int i = 0; i < 3; ++i) w.Bool(def.relays[i]);
        w.EndArray();
        if (!def.devs.empty()) {
            w.Key("devs");
            w.StartObject();
            for (const auto& kv : def.devs) {
                w.Key(kv.first.c_str());
                w.StartArray();
                for (size_t i = 0; i < 3; ++i) {
                    w.Bool(i < kv.second.size() ? kv.second[i] : false);
                }
                w.EndArray();
            }
            w.EndObject();
        }
        w.Key("desc"); w.String(def.desc.c_str());
        w.EndObject();
    }
    w.EndObject();
    ConfigStore::getInstance()->saveSceneJson(std::string(sb.GetString(), sb.GetSize()));
}

SceneDef* SceneManager::find(const std::string& name) {
    for (auto& def : mScenes) {
        if (def.name == name) return &def;
    }
    // 别名匹配：desc 形如 "回家模式:客厅+卧室开" -> 可用 "回家模式" 命中
    for (auto& def : mScenes) {
        size_t colon = def.desc.find(':');
        std::string alias = (colon == std::string::npos) ? def.desc : def.desc.substr(0, colon);
        if (!alias.empty() && alias == name) return &def;
    }
    return nullptr;
}

bool SceneManager::activate(const std::string& name, bool fromRemote,
                            const bool* relayStates) {
    SceneDef* def = find(name);
    const bool* states = nullptr;
    bool own[3] = {false, false, false};
    if (def != nullptr) {
        std::string oid = ConfigStore::getInstance()->deviceId();
        auto it = def->devs.find(oid);
        if (it != def->devs.end() && it->second.size() >= 3) {
            for (int i = 0; i < 3; ++i) own[i] = it->second[i];
            states = own;
        } else {
            states = def->relays;
        }
    } else if (relayStates != nullptr) {
        states = relayStates;   // 本地未定义: 按对端携带状态执行联动
    } else {
        LOGW("SceneManager: unknown scene '%s'", name.c_str());
        return false;
    }

    for (int i = 0; i < 3; ++i) {
        RelayManager::getInstance()->set(i + 1, states[i]);
    }
    mCurrent = name;
    LOGD("SceneManager: activate '%s' %s", name.c_str(),
         fromRemote ? "(remote linkage)" : "(local)");

    if (!fromRemote) {
        // 本地主机模式：走内嵌 broker 广播，从机按 devs 各自执行
        if (ConfigStore::getInstance()->runMode() == ConfigStore::MODE_MASTER) {
            LocalLink::getInstance()->publishScene(name);
            notify();
            return true;
        }
        // HA/单机模式：UDP 广播联动事件，全屋同情景设备一起执行
        rapidjson::StringBuffer sb;
        rapidjson::Writer<rapidjson::StringBuffer> w(sb);
        std::string id = ConfigStore::getInstance()->deviceId();
        w.StartObject();
        w.Key("event"); w.String("scene");
        w.Key("from");  w.String(id.c_str());
        w.Key("name");  w.String(name.c_str());
        w.Key("relays");
        w.StartArray();
        for (int i = 0; i < 3; ++i) w.Bool(states[i]);
        w.EndArray();
        w.EndObject();
        PanelLink::getInstance()->broadcast(std::string(sb.GetString(), sb.GetSize()));
    }

    notify();
    return true;
}

// 处理收到的广播联动事件（由 PanelLink 在解析 "event":"scene" 时调用）
// 注: 为保持模块单向依赖（SceneManager <- PanelLink），事件入口放在 PanelLink，
//     通过 activate(name, true, relays) 传入。

void SceneManager::defineScene(const std::string& name, const bool* relays,
                               const std::string& desc) {
    if (name.empty() || relays == nullptr) return;
    SceneDef* def = find(name);
    if (def == nullptr) {
        SceneDef d;
        d.name = name;
        mScenes.push_back(d);
        def = &mScenes.back();
    }
    def->desc = desc;
    memcpy(def->relays, relays, sizeof(def->relays));
    save();
    LOGD("SceneManager: scene '%s' defined", name.c_str());
    distribute();
    notify();
}

bool SceneManager::setSceneDevStates(const std::string& name, const std::string& devId,
                                     const bool states[3]) {
    if (name.empty() || devId.empty()) return false;
    SceneDef* def = find(name);
    if (def == nullptr) {
        SceneDef d;
        d.name = name;
        memset(d.relays, 0, sizeof(d.relays));
        mScenes.push_back(d);
        def = &mScenes.back();
    }
    std::vector<bool> st(3);
    for (int i = 0; i < 3; ++i) st[i] = states[i];
    def->devs[devId] = st;
    // devs 含定义者本机时同步 relays，保持 v1 字段为有效回退
    std::string oid = ConfigStore::getInstance()->deviceId();
    auto it = def->devs.find(oid);
    if (it != def->devs.end()) {
        for (int i = 0; i < 3; ++i) def->relays[i] = it->second[i];
    }
    save();
    distribute();
    notify();
    return true;
}

void SceneManager::importScenesJson(const std::string& json, bool merge) {
    if (json.empty()) return;
    rapidjson::Document doc;
    if (doc.Parse(json.c_str()).HasParseError() || !doc.IsObject()) return;
    if (!merge) mScenes.clear();
    std::vector<std::string> incoming;
    for (auto it = doc.MemberBegin(); it != doc.MemberEnd(); ++it) {
        if (!it->value.IsObject()) continue;
        incoming.push_back(it->name.GetString());
        SceneDef* def = find(it->name.GetString());
        if (def == nullptr) {
            SceneDef d;
            d.name = it->name.GetString();
            memset(d.relays, 0, sizeof(d.relays));
            mScenes.push_back(d);
            def = &mScenes.back();
        }
        if (it->value.HasMember("desc") && it->value["desc"].IsString()) {
            def->desc = it->value["desc"].GetString();
        }
        if (it->value.HasMember("relays") && it->value["relays"].IsArray()) {
            auto& arr = it->value["relays"];
            for (rapidjson::SizeType i = 0; i < arr.Size() && i < 3; ++i) {
                if (arr[i].IsBool()) def->relays[i] = arr[i].GetBool();
            }
        }
        if (it->value.HasMember("devs") && it->value["devs"].IsObject()) {
            def->devs.clear();
            for (auto d = it->value["devs"].MemberBegin(); d != it->value["devs"].MemberEnd(); ++d) {
                if (!d->value.IsArray()) continue;
                std::vector<bool> st;
                for (rapidjson::SizeType i = 0; i < d->value.Size() && i < 3; ++i) {
                    st.push_back(d->value[i].IsBool() ? d->value[i].GetBool() : false);
                }
                while (st.size() < 3) st.push_back(false);
                def->devs[d->name.GetString()] = st;
            }
        }
    }
    // merge 模式下删除主机已移除的情景
    if (merge) {
        for (size_t i = mScenes.size(); i > 0; --i) {
            const std::string& nm = mScenes[i - 1].name;
            bool found = false;
            for (const auto& k : incoming) {
                if (k == nm) { found = true; break; }
            }
            if (!found) mScenes.erase(mScenes.begin() + (i - 1));
        }
    }
    save();
    notify();
    LOGD("SceneManager: imported %d scenes (merge=%d)", (int)incoming.size(), merge ? 1 : 0);
}

void SceneManager::distribute() {
    if (ConfigStore::getInstance()->runMode() == ConfigStore::MODE_MASTER) {
        LocalLink::getInstance()->publishScenesConfig();
    }
}

std::vector<SceneDef> SceneManager::scenes() const {
    return mScenes;
}

std::string SceneManager::describe(const std::string& name) const {
    for (const auto& def : mScenes) {
        if (def.name == name) return def.desc;
    }
    return "";
}

void SceneManager::setListener(const std::function<void()>& listener) {
    mListener = listener;
}

void SceneManager::notify() {
    if (mListener) mListener();
}
