// 测试替身：MqttBridge
#ifndef _STUB_MQTT_BRIDGE_H_
#define _STUB_MQTT_BRIDGE_H_
#include <string>
class MqttBridge {
public:
    static MqttBridge* getInstance();
    void init();
    void stop();
    bool connected() const;
};
#endif
