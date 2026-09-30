/*
 * WebConfigServer.h -- 板内配置网页（钟工 2026-09-30）
 *
 * 为什么：HA 服务器的地址和「令牌」本来是写死在代码里的。改成可配置后，
 *   用面板键盘输一长串 token 太痛苦 —— 于是板子自己起一个很小的 HTTP 服务，
 *   面板上显示二维码，手机扫码打开网页，直接粘贴 token，点保存即可。
 *
 * 用法：
 *   WebConfigServer::getInstance()->start();          // 幂等，默认 8080
 *   WebConfigServer::getInstance()->pageUrl();        // http://<本机IP>:8080/<code>/（面板二维码内容）
 *
 * 路由（全部挂在 /<code>/ 下；code = ConfigStore::webCfgCode()）：
 *   GET  /<code>/            配置页（HTML，手机友好）
 *   POST /<code>/save        表单保存（application/x-www-form-urlencoded）-> 结果页
 *   GET  /<code>/status      当前状态 JSON（设备 ID / 模式 / 连接状态 / 已填服务器）
 *   其它路径                 404「请扫描面板上的二维码」
 *
 * 只监听本机所有网卡（同网段可达），明文 HTTP、无 TLS —— 面向局域网运维，
 * 与 MQTT 明文 1883 同一安全档位；口令码只防「同网段随手乱改」，不是鉴权。
 */
#ifndef SMART_PANEL_WEB_CONFIG_SERVER_H_
#define SMART_PANEL_WEB_CONFIG_SERVER_H_

#include <string>

class WebConfigServer {
public:
    static WebConfigServer* getInstance();

    void start(int port = 8080);          // 幂等；起一个 accept 线程
    void stop();
    bool running() const { return mRunning; }
    int port() const { return mPort; }

    // 面板二维码内容：http://<本机IP>:<port>/<code>/
    //   IP 取 wlan0 -> eth0 -> 其它非回环网卡；都没有时退回 127.0.0.1（日志提示）
    std::string pageUrl();
    std::string urlForIp(const std::string& ip);
    static std::string localIp();

private:
    WebConfigServer() = default;

    void loop();
    static void* threadEntry(void* self);

    void handleClient(int fd);
    // 返回 true 表示已处理（path 合法）
    bool route(const std::string& method, const std::string& rawPath,
               const std::string& body, std::string& out);

    bool mRunning = false;
    int mPort = 8080;
    int mListenFd = -1;
    unsigned long mThread = 0;
};

#endif  // SMART_PANEL_WEB_CONFIG_SERVER_H_
