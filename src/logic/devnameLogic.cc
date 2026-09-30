/*
 * devnameLogic.cc -- 「设备名称」修改页（devname.ftu）
 * 钟工 2026-09-25（问题单 09251751-7）：HA 上报的设备信息要用设置里的设备名称，
 * 后台才能区分设备；同时设备名称要支持修改。
 *
 * 保存后：ConfigStore::setDeviceName() -> MqttBridge::republishDiscovery()
 *        （HA Discovery 的 dev.name 立即更新为 retained）
 * 键盘：用系统内置键盘（ZKEditText 自动弹出，铁律 #2：不自绘键盘）。
 */
#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD

/**
 * @brief 串口数据回调接口
 */
static void onProtocolDataUpdate(const SProtocolData &data) {
  LOGD_TRACE("");
}
#pragma once

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "network/MqttBridge.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"
#include "control/ZKEditText.h"

#include <stdio.h>
#include <string>

#define DN_MAX_BYTES 72        // 最多 24 个汉字（UTF-8 3 字节/字）

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

// 去掉首尾空白
static std::string dnTrim(const std::string& s) {
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\n' || s[a] == '\r')) a++;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\n' || s[b - 1] == '\r')) b--;
    return s.substr(a, b - a);
}

// 按 UTF-8 字符边界截断（避免截出半个汉字）
static std::string dnFit(const std::string& s, size_t maxBytes) {
    std::string out;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        size_t len = (c < 0x80) ? 1 : ((c < 0xE0) ? 2 : ((c < 0xF0) ? 3 : 4));
        if (i + len > s.size()) break;
        if (out.size() + len > maxBytes) break;
        out.append(s, i, len);
        i += len;
    }
    return out;
}

static void dnRefresh() {
    ConfigStore* cfg = ConfigStore::getInstance();
    std::string cur = cfg->deviceName();
    if (mEditDnNamePtr != NULL) mEditDnNamePtr->setText(cur.c_str());
    if (mTextDnCurPtr != NULL) {
        std::string t = "当前：" + cur;
        mTextDnCurPtr->setText(t.c_str());
    }
}

static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    dnRefresh();
}

static void onUI_intent(const Intent* intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    dnRefresh();
}

static void onUI_hide() {}
static void onUI_quit() {}
static bool onUI_Timer(int id) { (void)id; return true; }
static bool ondevnameActivityTouchEvent(const MotionEvent& ev) { (void)ev; return false; }

static bool onButtonClick_ButtonDnBack(ZKButton* p) { (void)p; EASYUICONTEXT->goBack(); return true; }
static bool onButtonClick_ButtonDnCancel(ZKButton* p) { (void)p; EASYUICONTEXT->goBack(); return true; }

static bool onButtonClick_ButtonDnSave(ZKButton* p) {
    (void)p;
    std::string name = (mEditDnNamePtr != NULL) ? dnTrim(mEditDnNamePtr->getText()) : std::string();
    name = dnFit(name, DN_MAX_BYTES);
    if (name.empty()) {
        if (mTextDnHint1Ptr != NULL) mTextDnHint1Ptr->setText("名称不能为空");
        return true;
    }
    ConfigStore::getInstance()->setDeviceName(name);
    // 名称随 HA 上报：立刻重发 discovery（dev.name -> 新名称，retained）
    MqttBridge::getInstance()->republishDiscovery();
    LOGD("devname: saved '%s'", name.c_str());
    EASYUICONTEXT->goBack();
    return true;
}static void onEditTextChanged_EditDnName(const std::string &text) {
  LOGD_TRACE("EditDnName text changed %s", text.c_str());
}


