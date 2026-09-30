/*
 * MiniBroker.cpp - 极简 MQTT 3.1.1 broker 实现（见 MiniBroker.h）
 */
#include "network/MiniBroker.h"

#include "utils/Log.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <string.h>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>

MiniBroker* MiniBroker::getInstance() {
    static MiniBroker s;
    return &s;
}

// MQTT 包类型
enum {
    MQTT_CONNECT = 1, MQTT_CONNACK, MQTT_PUBLISH, MQTT_PUBACK,
    MQTT_SUBSCRIBE = 8, MQTT_SUBACK, MQTT_UNSUBSCRIBE = 10, MQTT_UNSUBACK,
    MQTT_PINGREQ = 12, MQTT_PINGRESP, MQTT_DISCONNECT = 14
};

bool MiniBroker::sendAll(int fd, const void* buf, size_t len) {
    const char* p = (const char*)buf;
    while (len > 0) {
        ssize_t n = send(fd, p, len, MSG_NOSIGNAL);
        if (n <= 0) return false;
        p += n;
        len -= (size_t)n;
    }
    return true;
}

static bool recvAll(int fd, void* buf, size_t len) {
    char* p = (char*)buf;
    while (len > 0) {
        ssize_t n = recv(fd, p, len, 0);
        if (n <= 0) return false;
        p += n;
        len -= (size_t)n;
    }
    return true;
}

// 读一个完整 MQTT 包：返回类型，body 填入 payload（不含固定头与长度字段）
// flags 输出固定头低 4 位（QoS/retain/DUP），供 PUBLISH 取 retain 位
static int readPacket(int fd, std::string& body, unsigned char* flags) {
    unsigned char h[1];
    if (!recvAll(fd, h, 1)) return -1;
    if (flags) *flags = h[0] & 0x0F;
    int type = (h[0] >> 4) & 0x0F;
    // remaining length 变长
    int mult = 1, rem = 0, count = 0;
    unsigned char b;
    do {
        if (!recvAll(fd, &b, 1)) return -1;
        rem += (b & 0x7F) * mult;
        mult *= 128;
    } while ((b & 0x80) && ++count < 4);
    if (rem > 1024 * 1024) return -1;
    body.resize(rem);
    if (rem > 0 && !recvAll(fd, &body[0], rem)) return -1;
    return type;
}

// 编码剩余长度
static size_t encodeRemLen(unsigned char* out, int len) {
    size_t n = 0;
    do {
        unsigned char b = len % 128;
        len /= 128;
        if (len > 0) b |= 0x80;
        out[n++] = b;
    } while (len > 0);
    return n;
}

bool MiniBroker::topicMatch(const std::string& filter, const std::string& topic) {
    size_t fi = 0, ti = 0;
    while (fi < filter.size()) {
        size_t fend = filter.find('/', fi);
        std::string fseg = filter.substr(fi, fend == std::string::npos ? std::string::npos : fend - fi);
        if (fseg == "#") return true;               // 末级匹配全部
        if (ti >= topic.size()) return false;
        size_t tend = topic.find('/', ti);
        std::string tseg = topic.substr(ti, tend == std::string::npos ? std::string::npos : tend - ti);
        if (fseg != "+" && fseg != tseg) return false;
        if (fend == std::string::npos) return tend == std::string::npos;
        fi = fend + 1;
        ti = tend + 1;
    }
    return ti >= topic.size();
}

bool MiniBroker::start(int port) {
    if (mRunning) return true;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;
    int on = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons((unsigned short)port);
    if (bind(fd, (struct sockaddr*)&addr, sizeof(addr)) != 0 || listen(fd, 16) != 0) {
        close(fd);
        LOGW("MiniBroker: bind/listen %d failed", port);
        return false;
    }
    mListenFd = fd;
    mRunning = true;
    std::thread(&MiniBroker::acceptLoop, this, fd).detach();
    LOGD("MiniBroker: listening on :%d", port);
    return true;
}

void MiniBroker::stop() {
    mRunning = false;
    if (mListenFd >= 0) {
        close(mListenFd);
        mListenFd = -1;
    }
    std::lock_guard<std::mutex> lk(mMutex);
    for (Client* c : mClients) {
        if (c->fd >= 0) close(c->fd);
        delete c;
    }
    mClients.clear();
    mRetained.clear();
}

void MiniBroker::acceptLoop(int listenFd) {
    while (mRunning) {
        struct sockaddr_in from;
        socklen_t flen = sizeof(from);
        int cfd = accept(listenFd, (struct sockaddr*)&from, &flen);
        if (cfd < 0) {
            if (mRunning) usleep(50 * 1000);
            continue;
        }
        Client* c = new Client();
        c->fd = cfd;
        std::thread(&MiniBroker::clientLoop, this, c).detach();
    }
}

void MiniBroker::addSub(Client* c, const std::string& filter) {
    std::lock_guard<std::mutex> lk(mMutex);
    for (const auto& f : c->subs) {
        if (f == filter) return;
    }
    c->subs.push_back(filter);
    // 补发匹配保留消息
    for (const auto& kv : mRetained) {
        if (topicMatch(filter, kv.first)) {
            std::string pkt;
            unsigned char hdr = 0x30;   // PUBLISH QoS0
            unsigned char lenbuf[4];
            size_t tlen = kv.first.size();
            pkt.reserve(2 + tlen + kv.second.size());
            pkt.push_back((char)hdr);
            int rem = (int)(2 + tlen + kv.second.size());
            size_t ln = encodeRemLen(lenbuf, rem);
            pkt.append((char*)lenbuf, ln);
            pkt.push_back((char)(tlen >> 8));
            pkt.push_back((char)(tlen & 0xFF));
            pkt.append(kv.first);
            pkt.append(kv.second);
            sendAll(c->fd, pkt.data(), pkt.size());
        }
    }
}

void MiniBroker::deliver(const std::string& topic, const std::string& payload, Client* from) {
    std::vector<Client*> targets;
    {
        std::lock_guard<std::mutex> lk(mMutex);
        for (Client* c : mClients) {
            if (!c->alive || c->fd < 0 || c == from) continue;
            for (const auto& f : c->subs) {
                if (topicMatch(f, topic)) {
                    targets.push_back(c);
                    break;
                }
            }
        }
    }
    std::string pkt;
    unsigned char lenbuf[4];
    size_t tlen = topic.size();
    int rem = (int)(2 + tlen + payload.size());
    pkt.push_back((char)0x30);
    size_t ln = encodeRemLen(lenbuf, rem);
    pkt.append((char*)lenbuf, ln);
    pkt.push_back((char)(tlen >> 8));
    pkt.push_back((char)(tlen & 0xFF));
    pkt.append(topic);
    pkt.append(payload);
    for (Client* c : targets) {
        if (!sendAll(c->fd, pkt.data(), pkt.size())) {
            c->alive = false;
        }
    }
}

void MiniBroker::publish(const std::string& topic, const std::string& payload, bool retain) {
    if (retain) {
        std::lock_guard<std::mutex> lk(mMutex);
        if (payload.empty()) mRetained.erase(topic);
        else mRetained[topic] = payload;
    }
    deliver(topic, payload, nullptr);
}

void MiniBroker::setPublishHook(
    const std::function<void(const std::string&, const std::string&)>& hook) {
    mHook = hook;
}

void MiniBroker::removeClient(Client* c) {
    {
        std::lock_guard<std::mutex> lk(mMutex);
        for (size_t i = 0; i < mClients.size(); ++i) {
            if (mClients[i] == c) {
                mClients.erase(mClients.begin() + i);
                break;
            }
        }
    }
    if (c->fd >= 0) close(c->fd);
    delete c;
}

void MiniBroker::clientLoop(Client* c) {
    {
        std::lock_guard<std::mutex> lk(mMutex);
        mClients.push_back(c);
    }
    // 首包必须是 CONNECT
    std::string body;
    unsigned char flags = 0;
    int type = readPacket(c->fd, body, &flags);
    if (type != MQTT_CONNECT) {
        removeClient(c);
        return;
    }
    // 解析 CONNECT：proto name, level, flags, keepalive, client id
    size_t pos = 0;
    auto rdU16 = [&]() -> int {
        if (pos + 2 > body.size()) return -1;
        int v = ((unsigned char)body[pos] << 8) | (unsigned char)body[pos + 1];
        pos += 2;
        return v;
    };
    auto rdStr = [&]() -> std::string {
        int len = rdU16();
        if (len < 0 || pos + (size_t)len > body.size()) return "";
        std::string s = body.substr(pos, len);
        pos += len;
        return s;
    };
    std::string proto = rdStr();
    (void)proto;
    if (pos + 4 > body.size()) {
        removeClient(c);
        return;
    }
    pos += 1;                    // protocol level
    pos += 1;                    // connect flags（免认证，忽略）
    rdU16();                     // keepalive
    c->id = rdStr();
    // CONNACK: session present=0, return code=0
    const unsigned char connack[] = {0x20, 0x02, 0x00, 0x00};
    if (!sendAll(c->fd, connack, sizeof(connack))) {
        removeClient(c);
        return;
    }
    LOGD("MiniBroker: client connected id=%s", c->id.c_str());

    while (mRunning && c->alive) {
        std::string pkt;
        type = readPacket(c->fd, pkt, &flags);
        if (type < 0) break;
        switch (type) {
        case MQTT_PINGREQ: {
            const unsigned char pong[] = {0xD0, 0x00};
            if (!sendAll(c->fd, pong, sizeof(pong))) c->alive = false;
            break;
        }
        case MQTT_DISCONNECT:
            c->alive = false;
            break;
        case MQTT_SUBSCRIBE: {
            size_t p = 0;
            if (p + 2 <= pkt.size()) p += 2;    // packet id
            while (p < pkt.size()) {
                int tlen = ((unsigned char)pkt[p] << 8) | (unsigned char)pkt[p + 1];
                p += 2;
                std::string filter = pkt.substr(p, tlen);
                p += tlen + 1;                   // + requested qos byte
                addSub(c, filter);
            }
            // SUBACK: pid + 0x00 (granted QoS0)
            unsigned char ack[5] = {0x90, 0x03, 0x00, 0x00, 0x00};
            ack[2] = (type == 0) ? 0 : ack[2];
            // packet id 回填（取第一个）
            if (pkt.size() >= 2) {
                ack[2] = (unsigned char)pkt[0];
                ack[3] = (unsigned char)pkt[1];
            }
            ack[4] = 0x00;
            if (!sendAll(c->fd, ack, sizeof(ack))) c->alive = false;
            break;
        }
        case MQTT_UNSUBSCRIBE: {
            size_t p = 2;                        // packet id
            while (p < pkt.size()) {
                int tlen = ((unsigned char)pkt[p] << 8) | (unsigned char)pkt[p + 1];
                p += 2;
                std::string filter = pkt.substr(p, tlen);
                p += tlen;
                std::lock_guard<std::mutex> lk(mMutex);
                for (size_t i = 0; i < c->subs.size(); ++i) {
                    if (c->subs[i] == filter) {
                        c->subs.erase(c->subs.begin() + i);
                        break;
                    }
                }
            }
            unsigned char ack[4] = {0xB0, 0x02, 0x00, 0x00};
            if (pkt.size() >= 2) {
                ack[2] = (unsigned char)pkt[0];
                ack[3] = (unsigned char)pkt[1];
            }
            if (!sendAll(c->fd, ack, sizeof(ack))) c->alive = false;
            break;
        }
        case MQTT_PUBLISH: {
            size_t tlen = ((unsigned char)pkt[0] << 8) | (unsigned char)pkt[1];
            std::string topic = pkt.substr(2, tlen);
            std::string payload = pkt.substr(2 + tlen);
            // retain 位：存保留存储（空 payload = 清除）
            if (flags & 0x01) {
                std::lock_guard<std::mutex> lk(mMutex);
                if (payload.empty()) mRetained.erase(topic);
                else mRetained[topic] = payload;
            }
            deliver(topic, payload, c);
            if (mHook) mHook(topic, payload);
            break;
        }
        default:
            break;   // 其余类型忽略
        }
    }
    LOGD("MiniBroker: client disconnected id=%s", c->id.c_str());
    removeClient(c);
}
