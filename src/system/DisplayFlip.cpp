/*
 * DisplayFlip.cpp -- 「设备倒装」实现（详见 DisplayFlip.h 顶部说明）
 *
 * 关键证据（本机实测，2026-09-27）：
 *   - libeasyui.so（Z20, easyui 2.6.0）：ConfigManager::setScreenRotate(int rot) 反汇编为
 *       zk_disp_set_rotate(rot / 90)；setTouchRotate(int rot) -> zk_event_set_touch_rotate(rot / 90)。
 *     zk_disp_set_rotate 走系统 disp 驱动的 set_rotate 钩子（本板非空，= fbdev 的 _fbdev_set_rotate），
 *     随后 zk_widget_invalidate() 触发全屏重绘；_fbdev_set_rotate 里 90/270 才换宽高，180 不换。
 *   - /lib/libmi_disp.so 导出 MI_DISP_SetVideoLayerRotateMode；头文件
 *     registry/public/z20/mi_disp/0.0.0/include/mi_disp.h（工程 include 路径里已有，libmi_disp.so 也已链接）。
 *     mi_disp_datatype.h：E_MI_DISP_ROTATE_NONE=0 / 90=1 / 180=2 / 270=3。
 */
#include "system/DisplayFlip.h"

#include "manager/ConfigManager.h"
#include "storage/StoragePreferences.h"
#include "utils/Log.h"

#include <cstring>

#include "mi_disp.h"

#undef LOG_TAG
#define LOG_TAG "DisplayFlip"

// 拼接墙/屏保视频都在 DISP 视频层 0（libzkmedia 的 v4 引擎与 simple 引擎都是层 0，只是输入端口不同）
#define FLIP_VIDEO_LAYER    0
#define FLIP_PREF_KEY       "sp_flip180"

namespace {

// EasyUI.cfg 里 rotateScreen 给的基准角（本板 0）。第一次调用时取一次并记住，
// 之后一律 base + (倒装 ? 180 : 0)，避免 setScreenRotate 自己改掉缓存后反复叠加。
int baseRotate() {
    static int sBase = -1;
    if (sBase < 0) {
        int r = CONFIGMANAGER->getScreenRotate();
        r = ((r % 360) + 360) % 360;
        // 归一到 0/90/180/270
        sBase = (r / 90) * 90;
        LOGI("base screen rotate (EasyUI.cfg) = %d", sBase);
    }
    return sBase;
}

}  // namespace

namespace DisplayFlip {

bool enabled() {
    // 双兼容：现场习惯写 0/1（int），配置页写 true/false（bool）
    return StoragePreferences::getBool(FLIP_PREF_KEY, false)
           || StoragePreferences::getInt(FLIP_PREF_KEY, 0) != 0;
}

int videoRotateMode() {
    return enabled() ? (int)E_MI_DISP_ROTATE_180 : (int)E_MI_DISP_ROTATE_NONE;
}

void applyUi() {
    const int rot = (baseRotate() + (enabled() ? 180 : 0)) % 360;
    // 幂等：已经是目标角就不重设（setScreenRotate 会触发全屏失效重绘，进页时别白闪一下）
    const int cur = CONFIGMANAGER->getScreenRotate();
    if (cur == rot) {
        LOGD("applyUi: already %d (flip180=%d) -> skip", rot, enabled() ? 1 : 0);
        return;
    }
    CONFIGMANAGER->setScreenRotate(rot);
    CONFIGMANAGER->setTouchRotate(rot);
    LOGI("applyUi: setScreenRotate(%d) + setTouchRotate(%d) [flip180=%d] -> readback screen=%d",
         rot, rot, enabled() ? 1 : 0, CONFIGMANAGER->getScreenRotate());
}

int applyVideoLayer() {
    MI_DISP_RotateConfig_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.eRotateMode = (MI_DISP_RotateMode_e)videoRotateMode();

    MI_S32 r = MI_DISP_SetVideoLayerRotateMode(FLIP_VIDEO_LAYER, &cfg);
    MI_S32 r1 = 0;
    if (r != MI_DISP_SUCCESS) {
        // 退让：万一视频层不是 0，试一下层 1（不影响任何在跑的播放器）
        r1 = MI_DISP_SetVideoLayerRotateMode(1, &cfg);
        LOGW("MI_DISP_SetVideoLayerRotateMode(layer=0, mode=%d) -> %d; layer=1 -> %d",
             (int)cfg.eRotateMode, (int)r, (int)r1);
    } else {
        LOGI("MI_DISP_SetVideoLayerRotateMode(layer=%d, mode=%d) -> %d (0=OK)",
             FLIP_VIDEO_LAYER, (int)cfg.eRotateMode, (int)r);
    }
    return (int)((r == MI_DISP_SUCCESS) ? r : r1);
}

void applyStored() {
    LOGI("applyStored: flip180=%d", enabled() ? 1 : 0);
    applyUi();
    applyVideoLayer();
}

bool setEnabled(bool on) {
    StoragePreferences::putBool(FLIP_PREF_KEY, on);
    LOGI("setEnabled(%d) persisted", on ? 1 : 0);
    applyUi();
    applyVideoLayer();
    return enabled() == on;
}

}  // namespace DisplayFlip
