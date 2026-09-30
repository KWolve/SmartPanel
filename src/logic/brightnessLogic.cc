#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * brightnessLogic.cc -- 屏幕亮度页（brightness.ftu）
 *
 * 两个亮度：
 *   (1) 工作页面亮度：主页/设置等页面亮度（保存后立即生效，并作为退出屏保时的恢复值）
 *   (2) 屏保亮度：进入屏保（main.ftu）时自动切到该亮度
 * 落盘走业务单例 ConfigStore（跨页共享，不互相操作控件）。
 */

#include "utils/Log.h"
#include "utils/BrightnessHelper.h"
#include "entry/EasyUIContext.h"
#include "control/ZKSeekBar.h"
#include "control/ZKTextView.h"
#include "control/ZKButton.h"
#include "storage/ConfigStore.h"

#include <stdio.h>

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static int sWork = 80;
static int sSs = 30;

// 滑条拖动回调（代码注册，不依赖生成的回调名）
class BrightListener : public ZKSeekBar::ISeekBarChangeListener {
public:
    explicit BrightListener(bool isSs) : mIsSs(isSs) {}
    virtual void onProgressChanged(ZKSeekBar *pSeekBar, int progress) {
        (void)pSeekBar;
        if (progress < 0) progress = 0;
        if (progress > 100) progress = 100;
        if (mIsSs) {
            sSs = progress;
            if (mTextBrSsValuePtr != NULL) {
                char b[16];
                snprintf(b, sizeof(b), "%d%%", progress);
                mTextBrSsValuePtr->setText(b);
            }
        } else {
            sWork = progress;
            if (mTextBrWorkValuePtr != NULL) {
                char b[16];
                snprintf(b, sizeof(b), "%d%%", progress);
                mTextBrWorkValuePtr->setText(b);
            }
            BRIGHTNESSHELPER->setBrightness(progress);   // 工作亮度实时可见
        }
    }
private:
    bool mIsSs;
};
static BrightListener sWorkListener(false);
static BrightListener sSsListener(true);

static void refreshValues() {
    char b[16];
    if (mTextBrWorkValuePtr != NULL) {
        snprintf(b, sizeof(b), "%d%%", sWork);
        mTextBrWorkValuePtr->setText(b);
    }
    if (mTextBrSsValuePtr != NULL) {
        snprintf(b, sizeof(b), "%d%%", sSs);
        mTextBrSsValuePtr->setText(b);
    }
    if (mSeekBrWorkPtr != NULL) mSeekBrWorkPtr->setProgress(sWork);
    if (mSeekBrSsPtr != NULL) mSeekBrSsPtr->setProgress(sSs);
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    ConfigStore* cfg = ConfigStore::getInstance();
    sWork = cfg->workBrightness();
    sSs = cfg->screensaverBrightness();
    if (mSeekBrWorkPtr != NULL) mSeekBrWorkPtr->setSeekBarChangeListener(&sWorkListener);
    if (mSeekBrSsPtr != NULL) mSeekBrSsPtr->setSeekBarChangeListener(&sSsListener);
    refreshValues();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    sWork = ConfigStore::getInstance()->workBrightness();
    sSs = ConfigStore::getInstance()->screensaverBrightness();
    refreshValues();
}

static void onUI_hide() {
}

static void onUI_quit() {
    if (mSeekBrWorkPtr != NULL) mSeekBrWorkPtr->setSeekBarChangeListener(NULL);
    if (mSeekBrSsPtr != NULL) mSeekBrSsPtr->setSeekBarChangeListener(NULL);
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) { (void)id; return true; }

static bool onbrightnessActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 按钮回调 ─────────────────────────────────────────────
static bool onButtonClick_ButtonBrBack(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->goBack();
    return true;
}

static bool onButtonClick_ButtonBrSave(ZKButton *pButton) {
    (void)pButton;
    ConfigStore* cfg = ConfigStore::getInstance();
    cfg->setWorkBrightness(sWork);
    cfg->setScreensaverBrightness(sSs);
    BRIGHTNESSHELPER->setBrightness(sWork);     // 工作亮度立即生效
    LOGD("brightness saved: work=%d ss=%d", sWork, sSs);
    EASYUICONTEXT->goBack();
    return true;
}

// 兼容生成器可能派发的命名（与上面代码注册的回调等价，做到两套都认）
static void onProgressChanged_SeekBrWork(ZKSeekBar *pSeekBar, int progress) {
    sWorkListener.onProgressChanged(pSeekBar, progress);
}
static void onProgressChanged_SeekBrSs(ZKSeekBar *pSeekBar, int progress) {
    sSsListener.onProgressChanged(pSeekBar, progress);
}
