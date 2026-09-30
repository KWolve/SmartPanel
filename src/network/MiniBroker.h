/*
 * MiniBroker.h - 极简 MQTT 3.1.1 broker（本地主机模式内嵌，免认证）
 *
 * 设计目标（P4）：Z20 作本地主机时无需外接 broker，同网段子设备/小程序
 * 直接连本机 1883 端口。按 128 连接设计。
 *
 * 支持：CONNECT/CONNACK、PINGREQ/PINGRESP、SUBSCRIBE/SUBACK(QoS0 授权)、
 *       UNSUBSCRIBE、PUBLISH（仅 QoS0，客户端->broker 转发 + RETAIN 存储，
 *       broker->客户端下行）、DISCONNECT。
 * 通配符：订阅过滤支持 "+" 单级与 "#" 末级多级。
 * 不支持：QoS1/2、 Will 消息、保留消息过期（纯内存，broker 停止即失）。
 *
 * 线程模型：accept 线程 + 每连接一个线程；订阅表/保留表全局互斥。
 */
#pragma once

#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <vector>

class MiniBroker {
public:
    static MiniBroker* getInstance();

    // 启动监听（幂等）。port 默认 1883。返回是否成功进入监听。
    bool start(int port = 1883);
    void stop();
    bool running() const { return mRunning; }

    // broker 侧发布（retained 可选）：情景下发/配置分发走这里
    void publish(const std::string& topic, const std::string& payload, bool retain);

    // 客户端 PUBLISH 钩子（topic, payload）：主机用它收集从机状态
    void setPublishHook(const std::function<void(const std::string&, const std::string&)>& hook);

private:
    MiniBroker() = default;

    struct Client {
        int fd = -1;
        std::string id;
        std::vector<std::string> subs;
        bool alive = true;
    };

    void acceptLoop(int listenFd);
    void clientLoop(Client* c);
    void deliver(const std::string& topic, const std::string& payload, Client* from);
    void addSub(Client* c, const std::string& filter);
    void removeClient(Client* c);

    static bool topicMatch(const std::string& filter, const std::string& topic);
    static bool sendAll(int fd, const void* buf, size_t len);

    volatile bool mRunning = false;
    int mListenFd = -1;
    std::mutex mMutex;
    std::map<std::string, std::string> mRetained;          // topic -> payload
    std::vector<Client*> mClients;
    std::function<void(const std::string&, const std::string&)> mHook;
};
