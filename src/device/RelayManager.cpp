/*
 * RelayManager.cpp -- 3 路继电器实现（映射表取自参考工程 Z20 面板）
 */
#include "device/RelayManager.h"

#include "storage/StoragePreferences.h"
#include "utils/GpioHelper.h"
#include "utils/Log.h"

// ── 硬件接线 ─────────────────────────────────────────────
// 方式一（推荐）：过零 IO 索引。参考工程实测（SW48480040D1）：
//   客厅灯(通道1) -> 过零输出索引 3｜卧室灯(2) -> 1｜灯带(3) -> 2
// 改接线时**只动这张表**。
#define RELAY_USE_ZERO_CROSS   1
#define RELAY_GPIO_PIN_1       "B_02"
#define RELAY_GPIO_PIN_2       "B_03"
#define RELAY_GPIO_PIN_3       "E_20"
#define RELAY_ACTIVE_LEVEL     1        // 1=高电平吸合

static const uint8_t kZeroIndexMap[RelayManager::kChannels] = { 3, 1, 2 };

#define KEY_RELAY_STATE "sp_relay_state"   // bitmask：bit0..2 = 通道1..3

RelayManager* RelayManager::getInstance() {
    static RelayManager s;
    return &s;
}

void RelayManager::init() {
    // 钟工 2026-09-30（153 现场「反复关灯」）：本函数被 main 页与 home 页的 onUI_init 各自调用，
    //   页面重建（拼墙/屏保循环切页）会反复重入 → 原来每次都 restore()，
    //   而 restore() 用缺省掩码 0 回写 → 每切一次页就把三路继电器写 OFF（现场=反复关灯）。
    //   修法：进程内只初始化一次，之后直接返回，不再碰硬件。
    if (mInitialized) {
        LOGD("RelayManager: init skipped (already initialized)");
        return;
    }
#if RELAY_USE_ZERO_CROSS
    int zeroNum = GpioHelper::getZeroIoNum();
    if (zeroNum >= kChannels) {
        mMode = 0;
        LOGD("RelayManager: zero-cross output mode, channels=%d", zeroNum);
    } else
#endif
    if (GpioHelper::output(RELAY_GPIO_PIN_1, 0) == 0) {
        mMode = 1;
        LOGD("RelayManager: GPIO output mode");
    } else {
        mMode = 2;
        LOGW("RelayManager: GPIO unavailable -> SIMULATION mode");
    }
    restore();
    mInitialized = true;
    LOGD("RelayManager: init done (mode=%d, listeners=%d)", mMode, listenerCount());
}

void RelayManager::restore() {
    // 钟工 2026-09-30 口径：**正常的时候让灯光保持原来的状态**。
    //   只有存在存档时才回写硬件；没有存档（键不存在）就一个电平都不写。
    //   哨兵 -1 = 键不存在（合法掩码只有 0..7），否则缺省 0 会把整排灯关掉。
    int mask = StoragePreferences::getInt(KEY_RELAY_STATE, -1);
    if (mask < 0) {
        for (int i = 0; i < kChannels; i++) mState[i] = false;
        LOGW("RelayManager: no stored relay state -> keep hardware untouched (no write)");
        return;
    }
    for (int i = 1; i <= kChannels; i++) {
        mState[i - 1] = ((mask >> (i - 1)) & 1) != 0;
        writeHardware(i, mState[i - 1]);
        LOGD("RelayManager: restore ch%d = %d", i, mState[i - 1] ? 1 : 0);
    }
    LOGD("RelayManager: restore mask=0x%x -> [%d,%d,%d]", mask,
         mState[0] ? 1 : 0, mState[1] ? 1 : 0, mState[2] ? 1 : 0);
}

bool RelayManager::set(int ch, bool on) {
    if (ch < 1 || ch > kChannels) return false;
    if (mState[ch - 1] == on) return true;
    mState[ch - 1] = on;
    writeHardware(ch, on);
    int mask = StoragePreferences::getInt(KEY_RELAY_STATE, 0);
    if (on) mask |= (1 << (ch - 1));
    else    mask &= ~(1 << (ch - 1));
    StoragePreferences::putInt(KEY_RELAY_STATE, mask);
    LOGD("RelayManager: relay %d -> %s (mode=%d)", ch, on ? "ON" : "OFF", mMode);
    notify(ch, on);
    return true;
}

// 转发给「UI 视觉单槽 + 全部业务监听」；先拷一份再回调，避免回调里增删监听导致迭代失效
void RelayManager::notify(int ch, bool on) {
    std::function<void(int, bool)> ui = mUiListener;
    std::vector<std::function<void(int, bool)> > anon = mAnonListeners;
    std::vector<std::function<void(int, bool)> > keyed;
    keyed.reserve(mKeyedListeners.size());
    for (std::map<std::string, std::function<void(int, bool)> >::const_iterator it =
             mKeyedListeners.begin(); it != mKeyedListeners.end(); ++it) {
        keyed.push_back(it->second);
    }
    if (ui) ui(ch, on);
    for (size_t i = 0; i < anon.size(); i++) {
        if (anon[i]) anon[i](ch, on);
    }
    for (size_t i = 0; i < keyed.size(); i++) {
        if (keyed[i]) keyed[i](ch, on);
    }
}

void RelayManager::notifyAll() {
    LOGD("RelayManager: notifyAll [%d,%d,%d] -> %d listener(s)",
         mState[0] ? 1 : 0, mState[1] ? 1 : 0, mState[2] ? 1 : 0, listenerCount());
    for (int i = 1; i <= kChannels; ++i) notify(i, mState[i - 1]);
}

bool RelayManager::get(int ch) const {
    if (ch < 1 || ch > kChannels) return false;
    return mState[ch - 1];
}

void RelayManager::toggle(int ch) {
    if (ch >= 1 && ch <= kChannels) set(ch, !mState[ch - 1]);
}

void RelayManager::writeHardware(int ch, bool on) {
    int level = on ? RELAY_ACTIVE_LEVEL : (1 - RELAY_ACTIVE_LEVEL);
    switch (mMode) {
    case 0:
        GpioHelper::zeroOutput(kZeroIndexMap[ch - 1], on);
        break;
    case 1: {
        const char* pins[kChannels] = { RELAY_GPIO_PIN_1, RELAY_GPIO_PIN_2, RELAY_GPIO_PIN_3 };
        GpioHelper::output(pins[ch - 1], level);
        break;
    }
    default:
        break;   // 模拟模式只走日志
    }
}

// UI 视觉单槽（覆盖）。**只影响 UI 槽，不再清业务监听**（旧版 clear() 会连带抹掉
// MqttBridge/PanelLink 的上报回调 —— 见 RelayManager.h 事故复盘）。
void RelayManager::setListener(const std::function<void(int, bool)>& listener) {
    mUiListener = listener;
    LOGD("RelayManager: ui listener set (total=%d)", listenerCount());
}

void RelayManager::addListener(const std::function<void(int, bool)>& listener) {
    mAnonListeners.push_back(listener);
    LOGD("RelayManager: anonymous listener added (total=%d)", listenerCount());
}

void RelayManager::addListener(const std::string& key,
                               const std::function<void(int, bool)>& listener) {
    mKeyedListeners[key] = listener;
    LOGD("RelayManager: listener '%s' registered (total=%d)", key.c_str(), listenerCount());
}

bool RelayManager::removeListener(const std::string& key) {
    std::map<std::string, std::function<void(int, bool)> >::iterator it =
        mKeyedListeners.find(key);
    if (it == mKeyedListeners.end()) return false;
    mKeyedListeners.erase(it);
    LOGD("RelayManager: listener '%s' removed (total=%d)", key.c_str(), listenerCount());
    return true;
}

int RelayManager::listenerCount() const {
    return (mUiListener ? 1 : 0) + (int)mAnonListeners.size() + (int)mKeyedListeners.size();
}

std::string RelayManager::listenerKeys() const {
    std::string s;
    for (std::map<std::string, std::function<void(int, bool)> >::const_iterator it =
             mKeyedListeners.begin(); it != mKeyedListeners.end(); ++it) {
        if (!s.empty()) s += ",";
        s += it->first;
    }
    return s;
}
