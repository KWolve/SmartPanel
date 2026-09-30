#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * modeLogic.cc - 运行模式子页（mode.ftu）
 *
 * 三选一（HA 模式 / 本地主机 / 本地从机），另备「从机指向的主机 IP」输入框。
 * 口径（设计说明书 双模式 P4）：
 *   - setRunMode(mode)：0=HA（外接 broker）/ 1=本地主机（本机内嵌 broker）/ 2=本地从机
 *   - 模式切换必须重建链路：LocalLink::start()（内部先 stop，再按新 runMode 起主机/从机）
 *   - 从机且主机 IP 为空 -> 红字提示「从机需填写主机 IP」，阻止保存
 * 选中态与主页设备卡同一套语言：绿卡 + 名称深色 + 右上角对勾。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"
#include "control/ZKEditText.h"
#include "control/ZKQrcode.h"
#include "storage/ConfigStore.h"
#include "network/LocalLink.h"
#include "network/MqttBridge.h"
#include "network/WebConfigServer.h"

#include <stdio.h>
#include <string>

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

#define CLR_MODE_ON   0x10141A      // 绿卡上的深色字
#define CLR_MODE_NAME 0xECECF0      // 常态卡名称
#define CLR_MODE_DESC 0x9A9AA2      // 常态卡说明

static int sMode = ConfigStore::MODE_HA;

static ZKTextView* cardBg(int i) {
    ZKTextView* a[3] = { mImageModeCardBg1Ptr, mImageModeCardBg2Ptr, mImageModeCardBg3Ptr };
    return (i >= 0 && i < 3) ? a[i] : NULL;
}
static ZKTextView* cardChk(int i) {
    ZKTextView* a[3] = { mImageModeCardChk1Ptr, mImageModeCardChk2Ptr, mImageModeCardChk3Ptr };
    return (i >= 0 && i < 3) ? a[i] : NULL;
}
static ZKTextView* cardName(int i) {
    ZKTextView* a[3] = { mTextModeCardName1Ptr, mTextModeCardName2Ptr, mTextModeCardName3Ptr };
    return (i >= 0 && i < 3) ? a[i] : NULL;
}
static ZKTextView* cardDesc(int i, int j) {
    ZKTextView* a[9] = { mTextModeCardDesc1aPtr, mTextModeCardDesc1bPtr, mTextModeCardDesc1cPtr,
                         mTextModeCardDesc2aPtr, mTextModeCardDesc2bPtr, mTextModeCardDesc2cPtr,
                         mTextModeCardDesc3aPtr, mTextModeCardDesc3bPtr, mTextModeCardDesc3cPtr };
    int k = i * 3 + j;
    return (k >= 0 && k < 9) ? a[k] : NULL;
}

static std::string trimText(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return std::string();
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextModeTitlePtr, mTextModeTitleEnPtr,
        mImageModeCardBg1Ptr, mImageModeCardBg2Ptr, mImageModeCardBg3Ptr,
        mImageModeCardChk1Ptr, mImageModeCardChk2Ptr, mImageModeCardChk3Ptr,
        mTextModeCardName1Ptr, mTextModeCardName2Ptr, mTextModeCardName3Ptr,
        mTextModeCardDesc1aPtr, mTextModeCardDesc1bPtr, mTextModeCardDesc1cPtr,
        mTextModeCardDesc2aPtr, mTextModeCardDesc2bPtr, mTextModeCardDesc2cPtr,
        mTextModeCardDesc3aPtr, mTextModeCardDesc3bPtr, mTextModeCardDesc3cPtr,
        mTextModeIpLabelPtr, mTextModeIpHintPtr, mImageModeIpBgPtr,
        mTextModeErrPtr, mImageModeSaveBgPtr,
        // 扫码配置区（钟工 2026-09-30）：文字层同样放行触摸
        mTextModeQrTitlePtr, mTextModeQrUrlPtr, mTextModeQrHintPtr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

// 选中卡：绿卡 + 深色字 + 对勾；未选：常态卡 + 亮字，对勾隐藏
static void refreshCards() {
    for (int i = 0; i < 3; i++) {
        bool on = (i == sMode);
        ZKTextView* bg = cardBg(i);
        ZKTextView* nm = cardName(i);
        ZKTextView* ck = cardChk(i);
        if (bg != NULL) bg->setBackgroundPic(on ? "images/card_hl.9.png" : "images/card.9.png");
        if (nm != NULL) nm->setTextColor(on ? CLR_MODE_ON : CLR_MODE_NAME);
        if (ck != NULL) ck->setVisible(on);
        for (int j = 0; j < 3; j++) {
            ZKTextView* ds = cardDesc(i, j);
            if (ds != NULL) ds->setTextColor(on ? CLR_MODE_ON : CLR_MODE_DESC);
        }
    }
}

static std::string sQrUrl;      // 已加载的二维码内容（变了才重新生成，QR 重算很贵）

// HA 模式：显示「扫码配置服务器」二维码（内容 = 板内网页地址，含本机 IP + 口令码）
// 其它模式：显示主机 IP 输入行（HA 模式下这一行换成二维码区）
static void refreshQr() {
    bool ha = (sMode == ConfigStore::MODE_HA);
    ZKTextView* qrText[] = { mTextModeQrTitlePtr, mTextModeQrUrlPtr, mTextModeQrHintPtr };
    for (size_t i = 0; i < sizeof(qrText) / sizeof(qrText[0]); i++) {
        if (qrText[i] != NULL) qrText[i]->setVisible(ha);
    }
    if (mQrcodeModeHaPtr != NULL) mQrcodeModeHaPtr->setVisible(ha);

    // 主机 IP 行：非 HA 模式可见（原行为保留）
    bool showIp = !ha;
    if (mTextModeIpLabelPtr != NULL) mTextModeIpLabelPtr->setVisible(showIp);
    if (mTextModeIpHintPtr != NULL) mTextModeIpHintPtr->setVisible(showIp);
    if (mImageModeIpBgPtr != NULL) mImageModeIpBgPtr->setVisible(showIp);
    if (mEditModeIpPtr != NULL) mEditModeIpPtr->setVisible(showIp);

    if (!ha) {
        sQrUrl.clear();
        return;
    }
    std::string url = WebConfigServer::getInstance()->pageUrl();
    if (url == sQrUrl) return;
    sQrUrl = url;
    // 面板没联网（wlan0/eth0 都没 IP）时，不要给 127.0.0.1 这种手机打不开的地址：
    // 二维码先藏起来，文字提示等待联网。
    bool noIp = (url.find("127.0.0.1") != std::string::npos);
    if (mQrcodeModeHaPtr != NULL) {
        mQrcodeModeHaPtr->setVisible(!noIp);
        if (!noIp) mQrcodeModeHaPtr->loadQRCode(url.c_str());
    }
    if (mTextModeQrUrlPtr != NULL) {
        mTextModeQrUrlPtr->setText(noIp ? "等待面板联网（WiFi / 网线）..." : url.c_str());
    }
    LOGD("mode: ha config qr -> %s", url.c_str());
}

// 从机且没填主机 IP -> 红字提醒
static void refreshHint() {
    if (mTextModeErrPtr == NULL) return;
    if (sMode != ConfigStore::MODE_SLAVE) { mTextModeErrPtr->setText(""); return; }
    ConfigStore* cfg = ConfigStore::getInstance();
    std::string ip = (mEditModeIpPtr != NULL) ? trimText(mEditModeIpPtr->getText()) : std::string();
    bool need = ip.empty() && cfg->masterIp().empty();
    mTextModeErrPtr->setText(need ? "从机需填写主机 IP" : "");
}

static void loadFromStore() {
    ConfigStore* cfg = ConfigStore::getInstance();
    sMode = cfg->runMode();
    if (mEditModeIpPtr != NULL) mEditModeIpPtr->setText(cfg->masterIp().c_str());
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    sQrUrl.clear();   // 页面重建 -> 二维码内容要重新落到新控件上（缓存不能跨页面实例活）
    passDecorations();
    loadFromStore();
    refreshCards();
    refreshHint();
    refreshQr();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    loadFromStore();
    refreshCards();
    refreshHint();
    refreshQr();
}

static void onUI_hide() {}
// 钟工 2026-09-30："HA 模式下二维码经常不显示，需要切换一下再显示"。
//   根因：sQrUrl 是 static，控件在页面销毁时被置 NULL（generated 代码），下次进页新建控件，
//   而 refreshQr() 看到 url == sQrUrl 就直接 return -> 新控件里从没 loadQRCode -> 二维码空白；
//   切到其它模式时会 clear 缓存，于是"切换一下才显示"。
//   修法：页面销毁/重建时清缓存（让缓存生命周期与控件对齐）。
static void onUI_quit() {
    sQrUrl.clear();
}
static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }
static bool onUI_Timer(int id) { (void)id; refreshQr(); return true; }
static bool onmodeActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonModeBack(ZKButton *p) {
    (void)p;
    EASYUICONTEXT->goBack();
    return true;
}

static bool onButtonClick_ButtonModeCard1(ZKButton *p) {
    (void)p;
    sMode = ConfigStore::MODE_HA;
    refreshCards();
    refreshHint();
    refreshQr();
    return true;
}
static bool onButtonClick_ButtonModeCard2(ZKButton *p) {
    (void)p;
    sMode = ConfigStore::MODE_MASTER;
    refreshCards();
    refreshHint();
    refreshQr();
    return true;
}
static bool onButtonClick_ButtonModeCard3(ZKButton *p) {
    (void)p;
    sMode = ConfigStore::MODE_SLAVE;
    refreshCards();
    refreshHint();
    refreshQr();
    return true;
}

static bool onButtonClick_ButtonModeSave(ZKButton *p) {
    (void)p;
    ConfigStore* cfg = ConfigStore::getInstance();
    std::string ip = (mEditModeIpPtr != NULL) ? trimText(mEditModeIpPtr->getText())
                                              : std::string();
    if (sMode == ConfigStore::MODE_SLAVE) {
        if (ip.empty()) ip = cfg->masterIp();      // 输入框没填就沿用已存值
        if (ip.empty()) {
            if (mTextModeErrPtr != NULL) mTextModeErrPtr->setText("从机需填写主机 IP");
            LOGW("mode: slave without master ip, save blocked");
            return true;
        }
    }
    if (!ip.empty()) cfg->setMasterIp(ip);
    cfg->setRunMode(sMode);
    // 模式变了必须重建链路（start 内部先 stop 再按新 runMode 起主机/从机）
    LocalLink::getInstance()->start();
    // HA 模式：连外接 broker + 发 HA discovery；其他模式：断开外接 broker
    if (cfg->runMode() == ConfigStore::MODE_HA) {
        MqttBridge::getInstance()->init();
    } else {
        MqttBridge::getInstance()->stop();
    }
    LOGD("mode: saved runMode=%d masterIp=%s", cfg->runMode(), cfg->masterIp().c_str());
    EASYUICONTEXT->goBack();
    return true;
}

static void onEditTextChanged_EditModeIp(const std::string &text) {
    (void)text;
    refreshHint();
}
