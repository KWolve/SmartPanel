/*
 * x86 测试替身（不参与真机构建）：只为实现 WebConfigServer 的依赖，跑通网页读写链路。
 * 放在 temp/，测完即弃。
 */
#ifndef _STUB_LOG_H_
#define _STUB_LOG_H_
#include <stdio.h>
#define LOGD(fmt, ...) printf("[D] " fmt "\n", ##__VA_ARGS__)
#define LOGI(fmt, ...) printf("[I] " fmt "\n", ##__VA_ARGS__)
#define LOGW(fmt, ...) printf("[W] " fmt "\n", ##__VA_ARGS__)
#define LOGE(fmt, ...) printf("[E] " fmt "\n", ##__VA_ARGS__)
#define LOGE_TRACE(fmt, ...) printf("[E] " fmt "\n", ##__VA_ARGS__)
#endif
