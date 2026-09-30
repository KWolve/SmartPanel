/*
 * stubs.cpp -- WebConfigServer 的 x86 测试替身（内存版配置）
 */
#include "storage/ConfigStore.h"
#include "network/MqttBridge.h"
#include "network/WebConfigServer.h"
#include "system/NetKeeper.h"

#include <stdio.h>
#include <unistd.h>
#include <string>

static std::string sServer, sUser, sPass;
static bool sEnabled = true;
static int sMode = ConfigStore::MODE_HA;

ConfigStore* ConfigStore::getInstance() {
    static ConfigStore s;
    return &s;
}
std::string ConfigStore::deviceId() { return "PANEL-TEST0001"; }
std::string ConfigStore::mqttPrefix() { return "smartpanel/" + deviceId(); }
std::string ConfigStore::webCfgCode() { return "AB12CD"; }
int ConfigStore::runMode() { return sMode; }
void ConfigStore::setRunMode(int m) { sMode = m; }
bool ConfigStore::mqttEnabled() { return sEnabled; }
std::string ConfigStore::mqttServer() { return sServer; }
std::string ConfigStore::mqttUser() { return sUser; }
std::string ConfigStore::mqttPassword() { return sPass; }
bool ConfigStore::mqttConfigured() { return !sServer.empty(); }
void ConfigStore::setMqttConfig(bool enabled, const std::string& server,
                                const std::string& user, const std::string& pass) {
    sEnabled = enabled;
    sServer = server;
    sUser = user;
    sPass = pass;
}

static bool sConnected = false;
MqttBridge* MqttBridge::getInstance() {
    static MqttBridge s;
    return &s;
}
void MqttBridge::init() { sConnected = true; }
void MqttBridge::stop() { sConnected = false; }
bool MqttBridge::connected() const { return sConnected; }

std::string NetKeeper_localIp() { return ""; }   // 故意置空：验证 wlan0 拿不到时回落到 eth0

// 测试驱动：以 127.0.0.1:18080 起服务，等外部 curl
int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    WebConfigServer::getInstance()->start(18080);
    printf("pageUrl=%s\n", WebConfigServer::getInstance()->pageUrl().c_str());
    fflush(stdout);
    while (1) sleep(1);
    return 0;
}
