// 测试替身：ConfigStore（真机实现见 projects/SmartPanel_HA/src/storage/ConfigStore.cpp）
#ifndef _STUB_CONFIG_STORE_H_
#define _STUB_CONFIG_STORE_H_

#include <string>

class ConfigStore {
public:
    static ConfigStore* getInstance();

    static const int MODE_HA = 0;
    static const int MODE_MASTER = 1;
    static const int MODE_SLAVE = 2;

    std::string deviceId();
    std::string mqttPrefix();
    std::string webCfgCode();

    int runMode();
    void setRunMode(int m);

    bool mqttEnabled();
    std::string mqttServer();
    std::string mqttUser();
    std::string mqttPassword();
    bool mqttConfigured();
    void setMqttConfig(bool enabled, const std::string& server,
                       const std::string& user, const std::string& pass);
};

#endif
