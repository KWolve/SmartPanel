#ifndef SMART_PANEL_NETKEEPER_H_
#define SMART_PANEL_NETKEEPER_H_

#include <string>

/*
 * NetKeeper -- 网络状态查询 + WiFi 保活（钟工 2026-09-24：程序只要在运行就必须能联网）
 *  - localIp()：读 wlan0 的真实 IPv4（没有则空串）
 *  - start()/stop()：起/停保活看门狗线程（幂等；5s 巡一次，断网则按候选命令重连 + 退避）
 * 只做"能联网"这一件事：查 IP -> 没 IP 就重连 -> 打日志，方便远程判断。
 */
std::string NetKeeper_localIp();
bool NetKeeper_online();
void NetKeeper_start();
void NetKeeper_stop();

#endif /* SMART_PANEL_NETKEEPER_H_ */
