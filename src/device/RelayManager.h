/*
 * RelayManager.h -- 3 路继电器（86 盒面板）
 *
 * 输出优先级：过零 IO（zeroOutput）-> GPIO 引脚 -> 模拟（仅日志）。
 * 状态持久化到 /data（StoragePreferences，bitmask），重启恢复断电前状态。
 * 任何来源（触摸 / 网络 / 情景）统一走 set()。
 */
#ifndef _DEVICE_RELAY_MANAGER_H_
#define _DEVICE_RELAY_MANAGER_H_

#include <functional>
#include <map>
#include <string>
#include <vector>

class RelayManager {
public:
    static const int kChannels = 3;

    static RelayManager* getInstance();

    void init();

    // init()/restore() 是否已跑过。用于让调用方「显式可观测」地处理未初始化，
    // 而不是静默拿到一屏 false（钟工 2026-09-27 问题单）。
    bool initialized() const { return mInitialized; }

    bool set(int ch, bool on);        // ch = 1..3
    bool get(int ch) const;
    void toggle(int ch);

    // 输出模式：0=过零IO 1=GPIO 2=模拟
    int outputMode() const { return mMode; }

    // ── 状态变化监听（钟工 2026-09-27 问题单：命令能到、状态不回发）──────────
    // 两条语义分开、互不覆盖：
    //   setListener()            = UI 视觉单槽（覆盖式，兼容旧代码：homeLogic 卡片刷新）
    //   addListener(fn)          = 业务匿名多路（追加）
    //   addListener(key, fn)     = 业务具名多路（同 key 覆盖 => 可重复调用，幂等）
    // 事故复盘：旧版 setListener() 会 clear() 整个列表，而 homeLogic::onUI_init()
    // （第一次进主页时执行）用 setListener() 刷卡片 —— 一进主页就把 MqttBridge 在
    // onConnected() 注册的状态上报回调抹掉，此后继电器再变化也不再回发 HA，
    // 于是 HA 侧命令下发后状态翻回旧值（"切过去一会儿又切回来"）。
    void setListener(const std::function<void(int, bool)>& listener);
    void addListener(const std::function<void(int, bool)>& listener);
    void addListener(const std::string& key, const std::function<void(int, bool)>& listener);
    bool removeListener(const std::string& key);

    int listenerCount() const;      // 排障可观测
    std::string listenerKeys() const;

    // 用当前真实状态逐个通知监听方（restore() 后主动对齐用；
    // 也保证"开机/重载后 retained 与实际一致"）
    void notifyAll();

private:
    RelayManager() = default;
    void writeHardware(int ch, bool on);
    void restore();
    void notify(int ch, bool on);

    bool mState[kChannels] = { false, false, false };
    bool mInitialized = false;
    int mMode = 2;
    std::function<void(int, bool)> mUiListener;
    std::vector<std::function<void(int, bool)> > mAnonListeners;
    std::map<std::string, std::function<void(int, bool)> > mKeyedListeners;
};

#endif // _DEVICE_RELAY_MANAGER_H_
