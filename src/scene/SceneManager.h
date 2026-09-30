/*
 * SceneManager.h
 *
 * 自定义情景模式 + 多设备联动。
 *
 * 情景 = 一组继电器状态 + 描述，持久化在 ConfigStore（JSON），
 * 可通过面板 UI、UDP API、MQTT 定义/触发。
 *
 * 情景 JSON v2（P4）：每台设备自行控制对应模式下的按键操作
 *   {"home": {"desc":"...", "relays":[1,1,0],
 *             "devs": {"PANEL-AAA":[1,1,0], "PANEL-BBB":[0,0,1]}}}
 *   relays = 定义者本机状态（向后兼容 v1）；devs = 指定设备的状态。
 *   设备执行时优先取 devs[本机ID]，否则回落 relays。
 *
 * 联动机制：
 *   本地主机模式：activate() -> LocalLink 广播 smartpanel/broadcast/scene，
 *     从机按 devs/relays 执行本机按键（不再 UDP 广播，避免双通道重复）。
 *   HA/单机模式：沿用 UDP 广播 {"event":"scene",...} 全屋联动。
 *   远程触发的事件不再二次广播，避免回环。
 */
#pragma once

#include <functional>
#include <map>
#include <string>
#include <vector>

struct SceneDef {
    std::string name;
    std::string desc;
    bool relays[3];
    // P4: 指定设备的状态（deviceId -> 3 路）；空 = 未指定，执行时回落 relays
    std::map<std::string, std::vector<bool> > devs;
};

class SceneManager {
public:
    static SceneManager* getInstance();

    void init();

    // 执行情景。fromRemote=true 表示来自外部联动（不再广播）。
    // 返回 false = 情景不存在且无法按携带状态执行。
    bool activate(const std::string& name, bool fromRemote,
                  const bool* relayStates = nullptr);

    // 定义/覆盖情景并持久化
    void defineScene(const std::string& name, const bool* relays,
                     const std::string& desc);

    // P4: 设置某情景下某设备的继电器状态（编辑用；hostOnly=true 仅本机执行项）
    bool setSceneDevStates(const std::string& name, const std::string& devId,
                           const bool states[3]);
    // P4: 直接采用外部情景定义 JSON（主机分发）。merge=true 保留本地额外情景
    void importScenesJson(const std::string& json, bool merge);

    std::vector<SceneDef> scenes() const;
    const std::string& currentScene() const { return mCurrent; }

    // 状态变化通知 UI
    void setListener(const std::function<void()>& listener);

    // 情景描述文本（UI 显示用）
    std::string describe(const std::string& name) const;

private:
    SceneManager() = default;
    void load();
    void save();
    void notify();
    SceneDef* find(const std::string& name);
    void distribute();            // 主机模式：retained 分发情景定义

    std::vector<SceneDef> mScenes;
    std::string mCurrent;
    std::function<void()> mListener;
};
