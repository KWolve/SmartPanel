#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * offLogic.cc - 关屏设置子页（off.ftu）
 *
 * 设计说明书 3.4.4（必选）：
 *   - 两个整点滑块：关屏开始 / 关屏结束（0..23）
 *   - 先后校验：起止相同 -> 红字提示 + 阻止保存（设置主页行值显示「时段无效 - 待设置」）
 *   - 支持跨零点（22:00 - 7:00）
 *   - 摘要行：每天 X:00 - Y:00 息屏 - 其他时间进入屏保
 * 落盘走业务单例 ConfigStore（跨页共享；屏保页 mainLogic 每秒按同一份配置判定息屏）。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "control/ZKSeekBar.h"
#include "control/ZKTextView.h"
#include "control/ZKButton.h"
#include "storage/ConfigStore.h"

#include <stdio.h>

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static int sStart = 0;      // 关屏开始（整点 0..23）
static int sEnd = 7;        // 关屏结束（整点 0..23）
static bool sEnable = true;

static void fmtHour(char* buf, size_t n, int hour) {
    snprintf(buf, n, "%02d:00", hour);
}

static void refreshChip() {
    if (mImageOffChip1Ptr != NULL) {
        mImageOffChip1Ptr->setBackgroundPic(sEnable ? "images/chip68x44_hl.png"
                                                    : "images/chip68x44.png");
    }
    if (mTextOffEnValuePtr != NULL) {
        mTextOffEnValuePtr->setText(sEnable ? "开启" : "关闭");
        mTextOffEnValuePtr->setTextColor(sEnable ? 0x10141A : 0xECECF0);
    }
}

// 摘要 + 校验提示（起止相同 -> 红字、禁存）
static bool refreshSummary() {
    char b[96];
    if (mTextOffStartValuePtr != NULL) {
        fmtHour(b, sizeof(b), sStart);
        mTextOffStartValuePtr->setText(b);
    }
    if (mTextOffEndValuePtr != NULL) {
        fmtHour(b, sizeof(b), sEnd);
        mTextOffEndValuePtr->setText(b);
    }
    bool valid = (sStart != sEnd);
    if (mTextOffSummaryPtr != NULL) {
        if (valid) {
            snprintf(b, sizeof(b), "每天 %02d:00 - %02d:00 息屏", sStart, sEnd);
            std::string s = std::string(b) + " - 其他时间进入屏保";
            if (!sEnable) s = std::string(b) + " - 关屏时段已关闭";
            mTextOffSummaryPtr->setText(s.c_str());
        } else {
            mTextOffSummaryPtr->setText("时段无效：开始与结束时间相同，请调整先后");
        }
    }
    if (mTextOffErrPtr != NULL) {
        mTextOffErrPtr->setText(valid ? "" : "开始与结束时间相同，请调整先后");
    }
    return valid;
}

class OffHourListener : public ZKSeekBar::ISeekBarChangeListener {
public:
    explicit OffHourListener(bool isStart) : mIsStart(isStart) {}
    virtual void onProgressChanged(ZKSeekBar *pSeekBar, int progress) {
        (void)pSeekBar;
        if (progress < ConfigStore::kOffHourMin) progress = ConfigStore::kOffHourMin;
        if (progress > ConfigStore::kOffHourMax) progress = ConfigStore::kOffHourMax;
        if (mIsStart) sStart = progress;
        else          sEnd = progress;
        refreshSummary();
    }
private:
    bool mIsStart;
};
static OffHourListener sStartListener(true);
static OffHourListener sEndListener(false);

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextOffTitlePtr, mTextOffTitleEnPtr, mImageOffRowBg1Ptr, mTextOffEnLabelPtr,
        mImageOffChip1Ptr, mTextOffEnValuePtr, mTextOffStartLabelPtr, mTextOffStartValuePtr,
        mTextOffEndLabelPtr, mTextOffEndValuePtr, mTextOffSummaryPtr, mTextOffHintPtr,
        mTextOffErrPtr, mImageOffSaveBgPtr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    ConfigStore* cfg = ConfigStore::getInstance();
    sStart = cfg->offStartHour();
    sEnd = cfg->offEndHour();
    sEnable = cfg->offEnabled();
    if (mSeekOffStartPtr != NULL) mSeekOffStartPtr->setSeekBarChangeListener(&sStartListener);
    if (mSeekOffEndPtr != NULL) mSeekOffEndPtr->setSeekBarChangeListener(&sEndListener);
    if (mSeekOffStartPtr != NULL) mSeekOffStartPtr->setProgress(sStart);
    if (mSeekOffEndPtr != NULL) mSeekOffEndPtr->setProgress(sEnd);
    passDecorations();
    refreshChip();
    refreshSummary();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    ConfigStore* cfg = ConfigStore::getInstance();
    sStart = cfg->offStartHour();
    sEnd = cfg->offEndHour();
    sEnable = cfg->offEnabled();
    if (mSeekOffStartPtr != NULL) mSeekOffStartPtr->setProgress(sStart);
    if (mSeekOffEndPtr != NULL) mSeekOffEndPtr->setProgress(sEnd);
    refreshChip();
    refreshSummary();
}

static void onUI_hide() {}

static void onUI_quit() {
    if (mSeekOffStartPtr != NULL) mSeekOffStartPtr->setSeekBarChangeListener(NULL);
    if (mSeekOffEndPtr != NULL) mSeekOffEndPtr->setSeekBarChangeListener(NULL);
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }
static bool onUI_Timer(int id) { (void)id; return true; }
static bool onoffActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonOffBack(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->goBack();
    return true;
}

static bool onButtonClick_ButtonOffRow1(ZKButton *pButton) {
    (void)pButton;
    sEnable = !sEnable;
    refreshChip();
    refreshSummary();
    return true;
}

static bool onButtonClick_ButtonOffSave(ZKButton *pButton) {
    (void)pButton;
    if (!refreshSummary()) {                 // 起止相同 -> 阻止保存
        LOGW("off: invalid period %d-%d, save blocked", sStart, sEnd);
        return true;
    }
    ConfigStore* cfg = ConfigStore::getInstance();
    cfg->setOffPeriod(sStart, sEnd);
    cfg->setOffEnabled(sEnable);
    LOGD("off: saved enable=%d %02d:00-%02d:00", sEnable ? 1 : 0, sStart, sEnd);
    EASYUICONTEXT->goBack();
    return true;
}

// 兼容生成器可能派发的滑条回调名
static void onProgressChanged_SeekOffStart(ZKSeekBar *pSeekBar, int progress) {
    sStartListener.onProgressChanged(pSeekBar, progress);
}
static void onProgressChanged_SeekOffEnd(ZKSeekBar *pSeekBar, int progress) {
    sEndListener.onProgressChanged(pSeekBar, progress);
}
