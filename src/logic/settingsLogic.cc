#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * settingsLogic.cc -- 设置主页（settings.ftu）
 *
 * 多 Activity 口径：本页只碰自己的控件；行点击 = openActivity(子页) / openActivity(系统 WiFi 页)。
 * 子页已接：运行模式(modeActivity)/屏幕亮度/关屏/屏保显示/屏保视频/相册上传/情景模式(scenesActivity)。
 */

#include "utils/Log.h"
#include "system/NetKeeper.h"
#include "system/DisplayFlip.h"
#include "utils/TimeHelper.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "wall/WallPlayer.h"

#include <stdio.h>
#include "window/ZKWindow.h"
#include "control/ZKTextView.h"
#include "control/ZKButton.h"

#define IDLE_ENTER_SEC 30          // 空闲回主页（心跳 tick 计时；不用墙钟，理由同 homeLogic）

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static long long sLastActivityMs = 0;
static int sIdleTicks = 0;      // 空闲心跳计数（触摸归零）
static long long nowMs() { return TimeHelper::getCurrentTime(); }
static void noteActivity() { sLastActivityMs = nowMs(); sIdleTicks = 0; }

// 行内文字/图标层放行触摸（行按钮在垫层之上，装饰件不得吃掉点击）
static void passRowDecorations() {
    ZKTextView* pass[] = {
        mTextSetTitlePtr, mTextSetTitleEnPtr,
        mTextGrpDevicePtr, mTextGrpSsPtr, mTextGrpSysPtr,
        mButtonRowWifiBgPtr, mButtonRowWifiIconBgPtr, mButtonRowWifiIconPtr, mButtonRowWifiLabelPtr, mButtonRowWifiValuePtr, mButtonRowWifiChevronPtr,
        mButtonRowModeBgPtr, mButtonRowModeIconBgPtr, mButtonRowModeIconPtr, mButtonRowModeLabelPtr, mButtonRowModeValuePtr, mButtonRowModeChevronPtr,
        mButtonRowNameBgPtr, mButtonRowNameIconBgPtr, mButtonRowNameIconPtr, mButtonRowNameLabelPtr, mButtonRowNameValuePtr, mButtonRowNameChevronPtr,
        mButtonRowScenesBgPtr, mButtonRowScenesIconBgPtr, mButtonRowScenesIconPtr, mButtonRowScenesLabelPtr, mButtonRowScenesValuePtr, mButtonRowScenesChevronPtr,
        mButtonRowBrightBgPtr, mButtonRowBrightIconBgPtr, mButtonRowBrightIconPtr, mButtonRowBrightLabelPtr, mButtonRowBrightValuePtr, mButtonRowBrightChevronPtr,
        mButtonRowOffBgPtr, mButtonRowOffIconBgPtr, mButtonRowOffIconPtr, mButtonRowOffLabelPtr, mButtonRowOffValuePtr, mButtonRowOffChevronPtr,
        mButtonRowSsSetBgPtr, mButtonRowSsSetIconBgPtr, mButtonRowSsSetIconPtr, mButtonRowSsSetLabelPtr, mButtonRowSsSetValuePtr, mButtonRowSsSetChevronPtr,
        mButtonRowVideoBgPtr, mButtonRowVideoIconBgPtr, mButtonRowVideoIconPtr, mButtonRowVideoLabelPtr, mButtonRowVideoValuePtr, mButtonRowVideoChevronPtr,
        mButtonRowAlbumBgPtr, mButtonRowAlbumIconBgPtr, mButtonRowAlbumIconPtr, mButtonRowAlbumLabelPtr, mButtonRowAlbumValuePtr, mButtonRowAlbumChevronPtr,
        // 按键配置行（钟工 2026-09-29）：同坑——整行要能点，装饰层必须放行
        mButtonRowKeySetBgPtr, mButtonRowKeySetIconBgPtr, mButtonRowKeySetIconPtr,
        mButtonRowKeySetLabelPtr, mButtonRowKeySetValuePtr, mButtonRowKeySetChevronPtr,
        mButtonRowVerBgPtr, mButtonRowVerIconBgPtr, mButtonRowVerIconPtr, mButtonRowVerLabelPtr, mButtonRowVerValuePtr, mButtonRowVerChevronPtr,
        // 多屏拼接行（新增行）：漏了这 4 层 -> 装饰件吃掉 DOWN，行中部点不进去（实测只有底缝/右缘能点）
        mImageRowWallBgPtr, mImageRowWallIconBgPtr, mImageRowWallIconPtr,
        mTextRowWallLabelPtr, mTextRowWallValuePtr, mTextRowWallChevronPtr,
        // 设备倒装行（钟工 2026-09-27）：同样必须全放行，否则行中部点不动
        mButtonRowFlipBgPtr, mButtonRowFlipIconBgPtr, mButtonRowFlipIconPtr,
        mButtonRowFlipLabelPtr, mButtonRowFlipValuePtr, mButtonRowFlipChevronPtr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

// ── 系统回调 ─────────────────────────────────────────────
// WiFi 行：显示真实联网状态（读 wlan0 的 IP；原来 json 里写死了 192.0.2.108）
static void refreshWifiRow() {
    if (mButtonRowWifiValuePtr == NULL) return;
    std::string ip = NetKeeper_localIp();
    std::string txt = ip.empty() ? std::string("未连接") : (std::string("已连接 - ") + ip);
    mButtonRowWifiValuePtr->setText(txt.c_str());
}

// 行值统一按 ConfigStore 刷新（子页保存后返回即时可见）
static void refreshRows() {
    ConfigStore* cfg = ConfigStore::getInstance();
    char b[96];

    if (mButtonRowNameValuePtr != NULL) mButtonRowNameValuePtr->setText(cfg->deviceName().c_str());

    // 多屏拼接行值（钟工 2026-09-25）：开/关 + 本机序号（存在 /data）
    if (mTextRowWallValuePtr != NULL) {
        bool en = StoragePreferences::getBool("sp_wall_en", false);
        int idx = StoragePreferences::getInt("sp_wall_idx", 1);
        int n = StoragePreferences::getInt("sp_wall_n", 2);
        char wb[64];
        if (en) {
            snprintf(wb, sizeof(wb), "已开启 %d/%d", idx, n);
        } else {
            snprintf(wb, sizeof(wb), "已关闭");
        }
        mTextRowWallValuePtr->setText(wb);
    }

    // 情景模式行值：原 json 是静态文案（"4 个情景 · 可增删"），从没被 setText；
    // 按运行模式给准确说法（HA 模式情景由 HA 管理，本页只读展示）
    if (mButtonRowScenesValuePtr != NULL) {
        bool ha = (ConfigStore::getInstance()->runMode() == ConfigStore::MODE_HA);
        mButtonRowScenesValuePtr->setText(ha ? "HA 情景 · 由 HA 执行" : "本机情景 · 可增删");
    }

    if (mButtonRowOffValuePtr != NULL) {
        if (!cfg->offPeriodValid()) {
            mButtonRowOffValuePtr->setText("时段无效 - 待设置");
        } else {
            snprintf(b, sizeof(b), "%s %02d:00-%02d:00 息屏",
                     cfg->offEnabled() ? "每天" : "已关闭",
                     cfg->offStartHour(), cfg->offEndHour());
            mButtonRowOffValuePtr->setText(b);
        }
    }

    if (mButtonRowBrightValuePtr != NULL) {
        snprintf(b, sizeof(b), "工作 %d%% - 屏保 %d%%", cfg->workBrightness(),
                 cfg->screensaverBrightness());
        mButtonRowBrightValuePtr->setText(b);
    }

    if (mButtonRowSsSetValuePtr != NULL) {
        const char* keys[5] = { "time", "date", "temphum", "weather", "statusbar" };
        int on = 0;
        for (int i = 0; i < 5; i++) if (cfg->ssItemVisible(keys[i], true)) on++;
        snprintf(b, sizeof(b), "%d 项开启 - 可增删", on);
        mButtonRowSsSetValuePtr->setText(b);
    }

    if (mButtonRowVideoValuePtr != NULL) {
        int iv = cfg->videoIntervalSec();
        const char* t = (iv == 0) ? "连续轮播" : "按间隔轮播";
        char vb[64];
        snprintf(vb, sizeof(vb), "%s - 图片 %d s", t, cfg->photoIntervalSec());
        mButtonRowVideoValuePtr->setText(vb);
    }

    // 相册上传行：跟相册页的「相册模式」开关联动（sp_album_mode）
    if (mButtonRowAlbumValuePtr != NULL) {
        bool on = StoragePreferences::getInt("sp_album_mode", 1) != 0;
        mButtonRowAlbumValuePtr->setText(on ? "相册模式已开启 - 点按进入" : "已关闭 - 点按进入");
    }

    // 设备倒装行值（钟工 2026-09-27）：开启 / 关闭（落盘在 /data 的 sp_flip180）
    if (mButtonRowFlipValuePtr != NULL) {
        bool on = DisplayFlip::enabled();
        mButtonRowFlipValuePtr->setText(on ? "开启 · 整屏已转 180°" : "关闭");
    }

    if (mButtonRowModeValuePtr != NULL) {
        int m = cfg->runMode();
        const char* t = (m == ConfigStore::MODE_MASTER) ? "本地主机 - 内嵌 Broker"
                        : (m == ConfigStore::MODE_SLAVE) ? "本地从机 - 接入主机"
                                                         : "HA 模式 - 订阅 HA";
        mButtonRowModeValuePtr->setText(t);
    }
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    refreshWifiRow();
    refreshRows();
    passRowDecorations();
    noteActivity();
}

static void onUI_intent(const Intent *intentPtr) {
    if (intentPtr != NULL) {
        // 从子页返回时可带参数刷新行值
    }
}

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    refreshWifiRow();
    refreshRows();          // 子页（关屏/亮度/屏保/视频/模式）保存返回后即时同步行值
    noteActivity();
}

static void onUI_hide() {
}

static void onUI_quit() {
}

static void onProtocolDataUpdate(const SProtocolData &data) {
    (void)data;
}

static bool onUI_Timer(int id) {
    // 钟工 2026-09-25（问题单 09251751-1）：设置页**不进屏保**，也不再空闲自动回主页。
    // 原来这里的 30s 空闲 -> goHome 已移除（与「只有主页进屏保」口径一致）。
    (void)id;
    return true;
}

static bool onsettingsActivityTouchEvent(const MotionEvent &ev) {
    if (ev.mActionStatus == MotionEvent::E_ACTION_DOWN || ev.mActionStatus == MotionEvent::E_ACTION_MOVE) {
        noteActivity();          // DOWN/MOVE 都算活动（滑动列表时不被抢回主页）
    }
    return false;
}

// ── 行回调 ───────────────────────────────────────────────
static bool onButtonClick_ButtonSetBack(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->goBack();
    return true;
}

static bool onButtonClick_ButtonRowWifi(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    // 本板固件里的系统网络设置页 activity = NetSettingActivity（钟工 2026-09-25 报告：原来写
    // zkwifisettingActivity 在本板不存在 -> 点击无效）
    EASYUICONTEXT->openActivity("NetSettingActivity");
    return true;
}

// 子页：运行模式（mode.ftu）/ 情景模式（scenes.ftu）
static bool onButtonClick_ButtonRowMode(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("modeActivity");
    return true;
}
static bool onButtonClick_ButtonRowWall(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    // 多屏拼接设置页（钟工 2026-09-25）
    EASYUICONTEXT->openActivity("wallActivity");
    return true;
}

static bool onButtonClick_ButtonRowName(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    // 钟工 2026-09-25（问题单 09251751-7）：设备名称可修改（子页 EditText + 系统键盘），
    // 保存后名称随 HA 上报（后台按设备名区分设备）。
    EASYUICONTEXT->openActivity("devnameActivity");
    return true;
}
static bool onButtonClick_ButtonRowScenes(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("scenesActivity");
    return true;
}
static bool onButtonClick_ButtonRowBright(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("brightnessActivity");
    return true;
}
static bool onButtonClick_ButtonRowOff(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("offActivity");
    return true;
}
static bool onButtonClick_ButtonRowSsSet(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("sssetActivity");
    return true;
}

static bool onButtonClick_ButtonRowKeySet(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("keysetActivity");
    return true;
}
static bool onButtonClick_ButtonRowAlbum(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("albumActivity");
    return true;
}
static bool onButtonClick_ButtonRowVer(ZKButton *pButton) { (void)pButton; LOGD("version row (no action)"); return true; }

// 设备倒装（钟工 2026-09-27 10:43）：点击即切换 + 立即生效（UI 转屏 / 触摸同转 / 视频层转）
//   ！顺序讲究：先落盘 -> 停播放器（DISP 层属性不能在播放中改，今天两段式起播的教训）
//      -> 转 UI/触摸 -> 转视频层；播放器由屏保页心跳自动重起（那时代码里已带新旋转）。
static bool onButtonClick_ButtonRowFlip(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    bool on = !DisplayFlip::enabled();
    StoragePreferences::putBool("sp_flip180", on);
    WallPlayer* wp = WallPlayer::getInstance();
    if (wp->running()) {
        LOGD("flip180: wall player running -> stop before MI layer rotate change");
        wp->stop();
    }
    DisplayFlip::applyUi();
    int r = DisplayFlip::applyVideoLayer();
    LOGI("flip180 toggled -> %d (ui+touch+videoLayer ret=%d)", on ? 1 : 0, r);
    refreshRows();
    return true;
}
static bool onButtonClick_ButtonRowVideo(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("videoActivity");
    return true;
}


