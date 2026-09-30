#include "device/SensorManager.h"

#include "storage/ConfigStore.h"
#include "utils/Log.h"
#include "utils/TimeHelper.h"

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// ── 天气接口预留 ──────────────────────────────────────────────
// 部署方申请密钥后，通过 UDP API 配置：{"cmd":"config_weather","url":"http://..."}
// 本类负责用 curl 拉取并把结果文本解析后交给 setWeather()。
static std::string sWeatherUrl;

SensorManager* SensorManager::getInstance() {
    static SensorManager s;
    return &s;
}

void SensorManager::init() {
    // 先显示上次缓存（重启瞬间不空白）
    mTemp = ConfigStore::getInstance()->cachedTemp();
    mHum  = ConfigStore::getInstance()->cachedHum();
    mWeather = ConfigStore::getInstance()->cachedWeather();
}

void SensorManager::setTempHum(float temp, float hum) {
    mExternal = true;
    if (temp < -40 || temp > 85 || hum < 0 || hum > 100) {
        LOGW("SensorManager: invalid data t=%.1f h=%.1f", temp, hum);
        return;
    }
    mTemp = temp;
    mHum = hum;
    ConfigStore::getInstance()->setCachedTempHum(temp, hum);
    notify();
}

void SensorManager::setWeather(const std::string& text) {
    if (text.empty()) return;
    mExternal = true;
    mWeather = text;
    ConfigStore::getInstance()->setCachedWeather(text);
    notify();
}

void SensorManager::setListener(const std::function<void()>& listener) {
    mListener = listener;
}

void SensorManager::notify() {
    if (mListener) mListener();
}

void SensorManager::demoTick() {
    // 每 5s 一次缓变（无外部传感器时的演示数据）
    long long now = TimeHelper::getCurrentTime();
    if (now - mLastDemoMs < 5000) return;
    mLastDemoMs = now;
    mTemp += (rand() % 11 - 5) / 10.0f;   // +/-0.5 随机游走
    if (mTemp < 18) mTemp = 18;
    if (mTemp > 32) mTemp = 32;
    mHum += (rand() % 11 - 5) / 10.0f;
    if (mHum < 30) mHum = 30;
    if (mHum > 75) mHum = 75;
    notify();
}

void SensorManager::fetchWeather(const std::string& url) {
    sWeatherUrl = url;
    if (sWeatherUrl.empty()) return;
    // 预留：curl -s "url" 拉取 JSON，解析后 setWeather("晴 26C");
    // 为避免阻塞 UI，实际拉取应放独立线程；此处仅保存配置并提示。
    LOGD("SensorManager: weather url configured = %s", sWeatherUrl.c_str());
}
