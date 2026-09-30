/*
 * SensorManager.h
 *
 * 温湿度 + 天气数据管理。
 * 数据来源（优先级从高到低）：
 *   1. 外部注入：UDP 广播 API / MQTT / 串口传感器解析后调用 setTempHum()
 *   2. 天气 HTTP 接口（预留，部署方配密钥后启用 fetchWeather()）
 *   3. 演示模式：缓变模拟值（出厂默认，便于无传感器联调）
 * 数据变化通过 listener 推给 UI 层。
 */
#pragma once

#include <functional>
#include <string>

class SensorManager {
public:
    static SensorManager* getInstance();

    void init();

    float temp() const { return mTemp; }
    float hum()  const { return mHum; }
    const std::string& weather() const { return mWeather; }

    // 外部数据注入（UDP API / MQTT / 串口）
    void setTempHum(float temp, float hum);
    void setWeather(const std::string& text);

    // 天气 HTTP 拉取（预留：部署方在 url 中填入自己的天气服务与密钥）
    void fetchWeather(const std::string& url);

    void setListener(const std::function<void()>& listener);

    // 演示模式缓变（由 UI 秒级定时器驱动；收到外部数据后自动失效）
    void demoTick();

private:
    SensorManager() = default;
    void notify();

    float mTemp = 25.0f;
    float mHum  = 50.0f;
    std::string mWeather = "未获取";
    bool mExternal = false;   // 收到外部数据后为 true，停止演示模拟
    long long mLastDemoMs = 0;
    std::function<void()> mListener;
};
