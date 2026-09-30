#include "entry/EasyUIContext.h"
#include "os/SystemProperties.h"
#include <string>
#include "uart/UartContext.h"
#include "manager/ConfigManager.h"
#include "network/WebConfigServer.h"      // 板内配置网页（钟工 2026-09-30）

#include <sys/mount.h>
#include <stdio.h>

// 与参考工程同款：launcher 在 initLib 阶段 dlopen 本库时，vold 可能还没把数据分区
// 挂到 /mnt/sdnand -> 构造函数（早于 initEasyUI 读资源/字体）里兜底挂载；
// 已挂载(EBUSY)或失败都静默继续 -- 视频侧会退到 /mnt/extsd/video（见 mainLogic::loadVideoList）。
__attribute__((constructor)) static void ensureSdnandMounted() {
    if (mount("/dev/block/mmcblk0p2", "/mnt/sdnand", "ext4",
              MS_RELATIME | MS_NOSUID | MS_NODEV, nullptr) != 0) {
        perror("ensureSdnandMounted");
    } else {
        printf("ensureSdnandMounted: mounted /dev/block/mmcblk0p2 -> /mnt/sdnand\n");
    }
}

#ifdef __cplusplus
extern "C" {
#endif  /* __cplusplus */

void onEasyUIInit(EasyUIContext *pContext) {
    // 初始化时打开串口
    UARTCONTEXT->openUart(CONFIGMANAGER->getUartName().c_str(), CONFIGMANAGER->getUartBaudRate());
    // 板内配置网页（钟工 2026-09-30）：HA 服务器地址/令牌不再写死，
    // 面板「运行模式 -> HA」页显示二维码，手机扫码后在网页里填写/粘贴。
    // 端口 8080（zkmqtt 状态页占 8084，相册上传占 9000）。
    WebConfigServer::getInstance()->start(8080);
}

void onEasyUIDeinit(EasyUIContext *pContext) {
    UARTCONTEXT->closeUart();
}

const char* onStartupApp(EasyUIContext *pContext) {
    (void)pContext;
    // 固定从主页（屏保页 mainActivity）启动。
    // 钟工 2026-09-25（问题单 09251751-2）：**去掉按属性调试起指定页**的功能——
    // 触摸注入已可自动化导航，留着该入口反而会在测试时把面板卡在子页（回不了主页）。
    static std::string sStartup = "mainActivity";
    printf("onStartupApp -> %s\n", sStartup.c_str());
    return sStartup.c_str();
}

#ifdef __cplusplus

}

#endif /* __cplusplus */
