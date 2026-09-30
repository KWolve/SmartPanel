/*
 * WebConfigServer.cpp -- 见 WebConfigServer.h
 */
#include "network/WebConfigServer.h"

#include "network/MqttBridge.h"
#include "storage/ConfigStore.h"
#include "system/NetKeeper.h"
#include "utils/Log.h"

#include <arpa/inet.h>
#include <errno.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <string>
#include <vector>

#define WCS_MAX_HEAD  8192
#define WCS_MAX_BODY  4096

WebConfigServer* WebConfigServer::getInstance() {
    static WebConfigServer s;
    return &s;
}

// ── 小工具 ─────────────────────────────────────────────────
static std::string trim(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return std::string();
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

// 去掉全部空白（令牌粘贴常见换行/空格）
static std::string stripSpace(const std::string& s) {
    std::string o;
    for (size_t i = 0; i < s.size(); i++) {
        char c = s[i];
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') continue;
        o += c;
    }
    return o;
}

static int hexVal(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static std::string urlDecode(const std::string& s) {
    std::string o;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == '+') { o += ' '; continue; }
        if (s[i] == '%' && i + 2 < s.size()) {
            int h = hexVal(s[i + 1]), l = hexVal(s[i + 2]);
            if (h >= 0 && l >= 0) { o += (char)(h * 16 + l); i += 2; continue; }
        }
        o += s[i];
    }
    return o;
}

static std::string formValue(const std::string& body, const std::string& key) {
    std::string out;
    size_t pos = 0;
    while (pos < body.size()) {
        size_t amp = body.find('&', pos);
        if (amp == std::string::npos) amp = body.size();
        std::string kv = body.substr(pos, amp - pos);
        pos = amp + 1;
        size_t eq = kv.find('=');
        if (eq == std::string::npos) continue;
        std::string k = urlDecode(kv.substr(0, eq));
        if (k == key) return urlDecode(kv.substr(eq + 1));
    }
    return out;
}

static std::string htmlEsc(const std::string& s) {
    std::string o;
    for (size_t i = 0; i < s.size(); i++) {
        switch (s[i]) {
            case '&': o += "&amp;"; break;
            case '<': o += "&lt;"; break;
            case '>': o += "&gt;"; break;
            case '"': o += "&quot;"; break;
            case '\'': o += "&#39;"; break;
            default: o += s[i];
        }
    }
    return o;
}

static std::string jsonEsc(const std::string& s) {
    std::string o;
    char b[8];
    for (size_t i = 0; i < s.size(); i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
        else if (c < 0x20) { snprintf(b, sizeof(b), "\\u%04x", c); o += b; }
        else o += (char)c;
    }
    return o;
}

// 地址归一化：允许用户只填 192.0.2.10 或 192.0.2.10:1883
static std::string normalizeServer(const std::string& in) {
    std::string s = stripSpace(in);
    if (s.empty()) return s;
    if (s.find("://") == std::string::npos) s = "mqtt://" + s;
    // 协议后没有端口 -> 补默认 1883
    size_t p = s.find("://");
    std::string hostPart = s.substr(p + 3);
    if (hostPart.find(':') == std::string::npos && !hostPart.empty()) s += ":1883";
    return s;
}

static const char* modeName(int m) {
    switch (m) {
        case ConfigStore::MODE_HA: return "HA 模式（外接 broker）";
        case ConfigStore::MODE_MASTER: return "本地主机";
        case ConfigStore::MODE_SLAVE: return "本地从机";
        default: return "未知";
    }
}

// ── 页面 ───────────────────────────────────────────────────
static const char* kPageCss =
    "<style>"
    "*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}"
    "body{margin:0;padding:18px 14px 40px;background:#0f1115;color:#e8e8ee;"
    "font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC',"
    "'Microsoft YaHei',sans-serif}"
    "h1{font-size:19px;margin:0 0 4px}.sub{color:#8d8d99;font-size:13px;margin-bottom:16px}"
    "label{display:block;font-size:13px;color:#9fa0ad;margin:14px 0 6px}"
    "input,textarea{width:100%;padding:11px 12px;border-radius:10px;border:1px solid #2c2f38;"
    "background:#171a21;color:#f2f2f7;font-size:15px;font-family:inherit}"
    "textarea{min-height:96px;resize:vertical;word-break:break-all}"
    "input:focus,textarea:focus{outline:none;border-color:#3f8cff}"
    "button{width:100%;margin-top:20px;padding:14px;border:0;border-radius:12px;"
    "background:#3f8cff;color:#fff;font-size:16px;font-weight:600}"
    "button:active{background:#2f6fd0}"
    ".card{margin-top:18px;padding:14px;border-radius:12px;background:#171a21;border:1px solid #24262e}"
    ".row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;font-size:13px}"
    ".row span:first-child{color:#8d8d99;flex:0 0 34%}"
    ".row span:last-child{word-break:break-all;text-align:right}"
    ".ok{color:#3ddc84}.bad{color:#ff6b6b}"
    ".tip{color:#8d8d99;font-size:12px;margin-top:14px}"
    ".chk{display:flex;align-items:center;gap:10px;margin-top:16px}"
    ".chk input{width:auto}"
    "</style>";

// 取网卡 IPv4（拿不到返回空串）
static std::string ipOfIface(const char* name) {
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return std::string();
    struct ifreq ifr;
    ::memset(&ifr, 0, sizeof(ifr));
    ::strncpy(ifr.ifr_name, name, IFNAMSIZ - 1);
    std::string out;
    if (::ioctl(fd, SIOCGIFADDR, &ifr) == 0) {
        struct sockaddr_in* sin = (struct sockaddr_in*)&ifr.ifr_addr;
        out = ::inet_ntoa(sin->sin_addr);
    }
    ::close(fd);
    if (out == "0.0.0.0") out.clear();
    return out;
}

// 面板的 IP（二维码/网址用）：
//   wlan0（主用 WiFi）-> eth0（Z20 有百兆网口，客户可能走网线）-> 其它非回环 IPv4
//   ⚠️ 不能只用 NetKeeper_localIp()：那个只读 wlan0，接网线时会拿到空 -> 二维码变成 127.0.0.1（手机扫了打不开）。
std::string WebConfigServer::localIp() {
    const char* cands[] = { "wlan0", "eth0", NULL };
    for (int i = 0; cands[i] != NULL; i++) {
        std::string ip = ipOfIface(cands[i]);
        if (!ip.empty()) return ip;
    }
    struct ifaddrs* ifs = NULL;
    if (::getifaddrs(&ifs) == 0 && ifs != NULL) {
        std::string out;
        for (struct ifaddrs* p = ifs; p != NULL; p = p->ifa_next) {
            if (p->ifa_addr == NULL || p->ifa_addr->sa_family != AF_INET) continue;
            if ((p->ifa_flags & IFF_LOOPBACK) != 0) continue;
            std::string name = p->ifa_name ? p->ifa_name : "";
            if (name == "lo") continue;
            struct sockaddr_in* sin = (struct sockaddr_in*)p->ifa_addr;
            std::string ip = ::inet_ntoa(sin->sin_addr);
            if (!ip.empty() && ip != "0.0.0.0") { out = ip; break; }
        }
        ::freeifaddrs(ifs);
        if (!out.empty()) return out;
    }
    return std::string();
}

std::string WebConfigServer::urlForIp(const std::string& ip) {
    char buf[160];
    snprintf(buf, sizeof(buf), "http://%s:%d/%s/", ip.c_str(), mPort,
             ConfigStore::getInstance()->webCfgCode().c_str());
    return std::string(buf);
}

std::string WebConfigServer::pageUrl() {
    std::string ip = localIp();
    if (ip.empty()) {
        LOGW("WebConfigServer: no ip on wlan0/eth0, qr falls back to 127.0.0.1");
        ip = "127.0.0.1";
    }
    return urlForIp(ip);
}

static std::string buildPage() {
    ConfigStore* cfg = ConfigStore::getInstance();
    std::string server = cfg->mqttServer();
    std::string user = cfg->mqttUser();
    std::string pass = cfg->mqttPassword();
    bool en = cfg->mqttEnabled();

    std::string h;
    h += "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">";
    h += "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">";
    h += "<title>SmartPanel 配置</title>";
    h += kPageCss;
    h += "</head><body>";
    h += "<h1>SmartPanel 配置</h1>";
    h += "<div class=\"sub\">设备 ";
    h += htmlEsc(cfg->deviceId());
    h += " · 当前模式 ";
    h += htmlEsc(modeName(cfg->runMode()));
    h += "</div>";

    h += "<form method=\"post\" action=\"save\" autocomplete=\"off\">";
    h += "<label>服务器地址（MQTT / Home Assistant Broker）</label>";
    h += "<input name=\"server\" value=\"";
    h += htmlEsc(server);
    h += "\" placeholder=\"mqtt://192.0.2.10:1883\" inputmode=\"url\">";

    h += "<label>用户名（可留空）</label>";
    h += "<input name=\"user\" value=\"";
    h += htmlEsc(user);
    h += "\" placeholder=\"homeassistant\">";

    h += "<label>密码 / 令牌（长令牌可直接粘贴，会自动去掉换行和空格）</label>";
    h += "<textarea name=\"pass\" placeholder=\"粘贴 MQTT 密码或访问令牌\">";
    h += htmlEsc(pass);
    h += "</textarea>";

    h += "<div class=\"chk\"><input type=\"checkbox\" id=\"en\" name=\"enabled\" value=\"1\"";
    if (en) h += " checked";
    h += "><label for=\"en\" style=\"margin:0\">启用 HA 连接</label></div>";

    h += "<button type=\"submit\">保存</button>";
    h += "</form>";

    h += "<div class=\"card\">";
    h += "<div class=\"row\"><span>设备 ID</span><span>";
    h += htmlEsc(cfg->deviceId());
    h += "</span></div>";
    h += "<div class=\"row\"><span>主题前缀</span><span>";
    h += htmlEsc(cfg->mqttPrefix());
    h += "</span></div>";
    h += "<div class=\"row\"><span>连接状态</span><span id=\"st\">读取中…</span></div>";
    h += "</div>";

    h += "<div class=\"tip\">服务器与令牌只保存在这台设备本地，不会上传到任何服务器。"
         "保存后面板会自动重连（HA 模式下生效）。</div>";

    // 状态轮询（不依赖外网，只打本机）
    h += "<script>function poll(){fetch('status',{cache:'no-store'}).then(function(r){"
         "return r.json()}).then(function(d){var e=document.getElementById('st');"
         "if(!d.enabled){e.textContent='已停用';e.className='bad';return;}"
         "if(!d.server){e.textContent='未配置服务器';e.className='bad';return;}"
         "if(d.connected){e.textContent='已连接';e.className='ok';}"
         "else{e.textContent='未连接（重试中）';e.className='bad';}}).catch(function(){});}"
         "poll();setInterval(poll,3000);</script>";
    h += "</body></html>";
    return h;
}

static std::string buildSavedPage(const std::string& msg, bool ok) {
    std::string h;
    h += "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">";
    h += "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">";
    h += "<title>已保存</title>";
    h += kPageCss;
    h += "</head><body><h1>";
    h += ok ? "已保存" : "保存失败";
    h += "</h1><div class=\"sub\">";
    h += htmlEsc(msg);
    h += "</div><div class=\"card\"><div class=\"row\"><span>连接状态</span><span id=\"st\">重连中…</span></div></div>";
    h += "<script>function poll(){fetch('status',{cache:'no-store'}).then(function(r){"
         "return r.json()}).then(function(d){var e=document.getElementById('st');"
         "if(d.connected){e.textContent='已连接';e.className='ok';}"
         "else{e.textContent='未连接（重试中）';e.className='bad';}}).catch(function(){});}"
         "poll();setInterval(poll,2000);</script>";
    h += "<p><a style=\"color:#3f8cff\" href=\"./\">返回配置页</a></p>";
    h += "</body></html>";
    return h;
}

static std::string buildStatusJson() {
    ConfigStore* cfg = ConfigStore::getInstance();
    char buf[512];
    std::string s = "{";
    s += "\"deviceId\":\"" + jsonEsc(cfg->deviceId()) + "\",";
    s += "\"ip\":\"" + jsonEsc(WebConfigServer::localIp()) + "\",";
    snprintf(buf, sizeof(buf), "\"runMode\":%d,\"modeName\":\"%s\",",
             cfg->runMode(), jsonEsc(modeName(cfg->runMode())).c_str());
    s += buf;
    s += "\"enabled\":" + std::string(cfg->mqttEnabled() ? "true" : "false") + ",";
    s += "\"server\":\"" + jsonEsc(cfg->mqttServer()) + "\",";
    s += "\"user\":\"" + jsonEsc(cfg->mqttUser()) + "\",";
    s += "\"hasPassword\":" + std::string(cfg->mqttPassword().empty() ? "false" : "true") + ",";
    s += "\"connected\":" + std::string(MqttBridge::getInstance()->connected() ? "true" : "false") + ",";
    s += "\"prefix\":\"" + jsonEsc(cfg->mqttPrefix()) + "\"";
    s += "}";
    return s;
}

// ── 路由 ───────────────────────────────────────────────────
bool WebConfigServer::route(const std::string& method, const std::string& rawPath,
                            const std::string& body, std::string& out) {
    std::string code = ConfigStore::getInstance()->webCfgCode();
    std::string base = "/" + code + "/";

    // 路径剥掉 query
    std::string path = rawPath;
    size_t q = path.find('?');
    if (q != std::string::npos) path = path.substr(0, q);

    if (path.compare(0, base.size(), base) != 0) {
        // 口令码不对（或没带）-> 明确提示，别让网页乱开
        out = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain; charset=utf-8\r\n"
              "Connection: close\r\n\r\n"
              "请扫描面板上的二维码打开配置页\n";
        return false;
    }
    std::string sub = path.substr(base.size());   // "" | "save" | "status"

    if (sub.empty() || sub == "index.html") {
        if (method == "GET") {
            std::string page = buildPage();
            char hdr[256];
            snprintf(hdr, sizeof(hdr),
                     "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                     "Cache-Control: no-store\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
                     (int)page.size());
            out = std::string(hdr) + page;
            return true;
        }
    } else if (sub == "status") {
        std::string js = buildStatusJson();
        char hdr[256];
        snprintf(hdr, sizeof(hdr),
                 "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                 "Cache-Control: no-store\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
                 (int)js.size());
        out = std::string(hdr) + js;
        return true;
    } else if (sub == "save" && method == "POST") {
        std::string server = normalizeServer(formValue(body, "server"));
        std::string user = trim(formValue(body, "user"));
        std::string pass = stripSpace(formValue(body, "pass"));
        bool enabled = !formValue(body, "enabled").empty();

        ConfigStore* cfg = ConfigStore::getInstance();
        cfg->setMqttConfig(enabled, server, user, pass);
        LOGD("WebConfigServer: saved server=[%s] user=[%s] passLen=%d enabled=%d",
             server.c_str(), user.c_str(), (int)pass.size(), enabled ? 1 : 0);

        // HA 模式：立刻按新配置重连（重连失败会由 MqttBridge::tick 退避续试）
        std::string msg;
        if (cfg->runMode() == ConfigStore::MODE_HA) {
            MqttBridge::getInstance()->stop();
            MqttBridge::getInstance()->init();
            msg = "配置已写入，面板正在连接服务器。";
        } else {
            msg = "配置已写入；当前不是 HA 模式，切到 HA 模式后生效。";
        }
        std::string page = buildSavedPage(msg, true);
        char hdr[256];
        snprintf(hdr, sizeof(hdr),
                 "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                 "Cache-Control: no-store\r\nContent-Length: %d\r\nConnection: close\r\n\r\n",
                 (int)page.size());
        out = std::string(hdr) + page;
        return true;
    }

    out = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain; charset=utf-8\r\n"
          "Connection: close\r\n\r\n"
          "no such page\n";
    return false;
}

// ── 连接处理 ───────────────────────────────────────────────
void WebConfigServer::handleClient(int fd) {
    struct timeval tv;
    tv.tv_sec = 5;
    tv.tv_usec = 0;
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    std::string req;
    char buf[1024];
    size_t headerEnd = std::string::npos;
    while (req.size() < WCS_MAX_HEAD) {
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        req.append(buf, (size_t)n);
        headerEnd = req.find("\r\n\r\n");
        if (headerEnd != std::string::npos) break;
    }
    if (headerEnd == std::string::npos) return;

    // 请求行
    size_t eol = req.find("\r\n");
    if (eol == std::string::npos) return;
    std::string line = req.substr(0, eol);
    size_t sp1 = line.find(' ');
    size_t sp2 = (sp1 == std::string::npos) ? std::string::npos : line.find(' ', sp1 + 1);
    if (sp1 == std::string::npos || sp2 == std::string::npos) return;
    std::string method = line.substr(0, sp1);
    std::string path = line.substr(sp1 + 1, sp2 - sp1 - 1);

    // Content-Length
    size_t contentLen = 0;
    std::string lower = req.substr(0, headerEnd);
    for (size_t i = 0; i < lower.size(); i++) lower[i] = (char)tolower((unsigned char)lower[i]);
    size_t cl = lower.find("content-length:");
    if (cl != std::string::npos) {
        contentLen = (size_t)strtoul(req.c_str() + cl + 15, NULL, 10);
        if (contentLen > WCS_MAX_BODY) contentLen = WCS_MAX_BODY;
    }

    std::string body = req.substr(headerEnd + 4);
    while (body.size() < contentLen) {
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        body.append(buf, (size_t)n);
    }

    std::string out;
    route(method, path, body, out);
    if (!out.empty()) {
        size_t off = 0;
        while (off < out.size()) {
            ssize_t n = ::send(fd, out.data() + off, out.size() - off, 0);
            if (n <= 0) break;
            off += (size_t)n;
        }
    }
}

void* WebConfigServer::threadEntry(void* self) {
    ((WebConfigServer*)self)->loop();
    return NULL;
}

void WebConfigServer::loop() {
    while (mRunning) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(mListenFd, &rfds);
        struct timeval tv;
        tv.tv_sec = 0;
        tv.tv_usec = 300 * 1000;
        int r = ::select(mListenFd + 1, &rfds, NULL, NULL, &tv);
        if (!mRunning) break;
        if (r <= 0) continue;
        struct sockaddr_in peer;
        socklen_t plen = sizeof(peer);
        int fd = ::accept(mListenFd, (struct sockaddr*)&peer, &plen);
        if (fd < 0) continue;
        handleClient(fd);
        ::close(fd);
    }
}

void WebConfigServer::start(int port) {
    if (mRunning) return;
    mPort = port;
    mListenFd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (mListenFd < 0) {
        LOGE("WebConfigServer: socket failed: %s", ::strerror(errno));
        return;
    }
    int on = 1;
    ::setsockopt(mListenFd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    struct sockaddr_in a;
    ::memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = ::htonl(INADDR_ANY);
    a.sin_port = ::htons((unsigned short)port);
    if (::bind(mListenFd, (struct sockaddr*)&a, sizeof(a)) < 0) {
        LOGE("WebConfigServer: bind :%d failed: %s", port, ::strerror(errno));
        ::close(mListenFd);
        mListenFd = -1;
        return;
    }
    if (::listen(mListenFd, 4) < 0) {
        LOGE("WebConfigServer: listen failed: %s", ::strerror(errno));
        ::close(mListenFd);
        mListenFd = -1;
        return;
    }
    mRunning = true;
    if (::pthread_create((pthread_t*)&mThread, NULL, threadEntry, this) != 0) {
        LOGE("WebConfigServer: pthread_create failed");
        mRunning = false;
        ::close(mListenFd);
        mListenFd = -1;
        return;
    }
    LOGI("WebConfigServer: listening on :%d, page %s", port, pageUrl().c_str());
}

void WebConfigServer::stop() {
    if (!mRunning) return;
    mRunning = false;
    if (mListenFd >= 0) { ::close(mListenFd); mListenFd = -1; }
    ::pthread_join((pthread_t)mThread, NULL);
    LOGD("WebConfigServer: stopped");
}
