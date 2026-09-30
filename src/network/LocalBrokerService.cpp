/*
 * LocalBrokerService.cpp - 见 LocalBrokerService.h
 */
#include "network/LocalBrokerService.h"
#include "utils/Log.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>

bool LocalBrokerService::sStartedByUs = false;

static const char* kCandidates[] = {
    "/mnt/sdnand/hub/bin/zkmqtt",
    "/res/bin/zkmqtt",
    "/tmp/zkmqtt",
};

bool LocalBrokerService::isRunning(int timeoutMs) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;
    struct timeval tv;
    tv.tv_sec = timeoutMs / 1000;
    tv.tv_usec = (timeoutMs % 1000) * 1000;
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
    struct sockaddr_in a;
    ::memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = ::htons(1883);
    a.sin_addr.s_addr = ::htonl(INADDR_LOOPBACK);
    bool ok = (::connect(fd, (struct sockaddr*)&a, sizeof(a)) == 0);
    ::close(fd);
    return ok;
}

std::string LocalBrokerService::binPath() {
    for (const char* p : kCandidates) {
        if (::access(p, X_OK) == 0) return std::string(p);
    }
    return std::string();
}

bool LocalBrokerService::ensureRunning(int waitMs) {
    if (isRunning()) return true;

    std::string bin = binPath();
    if (bin.empty()) {
        LOGW("LocalBrokerService: zkmqtt binary not found (checked /mnt/sdnand/hub/bin, /res/bin, /tmp)");
        return false;
    }

    // 先确保日志目录存在（sdnand 上的 hub/log）
    ::mkdir("/mnt/sdnand", 0777);
    ::mkdir("/mnt/sdnand/hub", 0777);
    ::mkdir("/mnt/sdnand/hub/log", 0777);

    pid_t pid = ::fork();
    if (pid < 0) {
        LOGW("LocalBrokerService: fork failed: %s", ::strerror(errno));
        return false;
    }
    if (pid == 0) {
        // 子进程：脱离会话 + 标准输出/错误进日志
        ::setsid();
        int logFd = ::open(logPath(), O_WRONLY | O_CREAT | O_APPEND, 0666);
        if (logFd >= 0) {
            ::dup2(logFd, STDOUT_FILENO);
            ::dup2(logFd, STDERR_FILENO);
            if (logFd > 2) ::close(logFd);
        }
        ::execl(bin.c_str(), "zkmqtt", "--mqtt", "1883", "--http", "8084",
                "--every", "30", (char*)nullptr);
        ::_exit(127);
    }

    // 父进程：等端口可连（最多 waitMs）
    int waited = 0;
    while (waited < waitMs) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        waited += 200;
        if (isRunning()) {
            sStartedByUs = true;
            LOGD("LocalBrokerService: %s started (pid=%d, waited %dms)",
                 bin.c_str(), (int)pid, waited);
            return true;
        }
    }
    // 起不来：回收僵尸并报错（调用方回退 MiniBroker）
    int st = 0;
    ::waitpid(pid, &st, WNOHANG);
    LOGW("LocalBrokerService: %s did not listen on :1883 within %dms (waitpid status=%d)",
         bin.c_str(), waitMs, st);
    return false;
}
