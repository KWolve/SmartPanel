# -*- coding: utf-8 -*-
"""屏保显示子页（ssset）：5 项显隐开关（时间/日期/温湿度/天气/设备状态条）存 /data + 设置页接线。
参考工程语义：ConfigStore::ssItemVisible(key, default) / key = time/date/temphum/weather/statusbar。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------- ① 生成器：加 build_ssset() ----------
p = os.path.join(ROOT, 'ui', '_gen', 'gen_pages.py')
t = open(p, encoding='utf-8').read()
assert 'def build_ssset' not in t

gen = '''

SS_ITEMS = [('time', '时间'), ('date', '日期'), ('temphum', '温湿度'),
            ('weather', '天气'), ('statusbar', '设备状态条')]


def build_ssset():
    """屏保显示：5 项显隐开关（点行切换，状态存 /data）+ 位置编辑提示。"""
    r = root_node()
    tv(r, 'TextSsSetTitle', (20, 12, 260, 30), '屏保显示', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextSsSetTitleEn', (20, 44, 300, 22), 'SCREENSAVER ITEMS', 18, C_DIM, AL_LT)
    btn(r, 'ButtonSsSetBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    for i, (key, label) in enumerate(SS_ITEMS):
        y = 84 + i * 52
        bgpic_layer(r, 'ImageSsSetRowBg%d' % (i + 1), (14, y, 452, 46), 'images/srow452x38.png')
        tv(r, 'TextSsSetRowLabel%d' % (i + 1), (34, y + 12, 260, 22), label, 18, C_TX, AL_LT)
        bgpic_layer(r, 'ImageSsSetChip%d' % (i + 1), (378, y + 5, 68, 44), 'images/chip68x44.png')
        btn(r, 'ButtonSsSetRow%d' % (i + 1), (14, y, 452, 46), '', C_TX, align=AL_LC)
        tv(r, 'TextSsSetRowValue%d' % (i + 1), (378, y + 5, 68, 44), '显示', 18, C_TX, AL_CC)

    tv(r, 'TextSsSetHint1', (20, 360, 440, 22), '点行切换显示/隐藏（立即生效并存 /data）', 16, C_SUB, AL_LT)
    tv(r, 'TextSsSetHint2', (20, 386, 440, 22), '位置编辑：后续版本支持拖动调整', 16, C_DIM, AL_LT)
    return r


PAGES = [('main.json', build_ss), ('home.json', build_home), ('settings.json', build_settings),
         ('brightness.json', build_brightness), ('video.json', build_video),
         ('album.json', build_album), ('ssset.json', build_ssset)]'''
t = t.replace('''PAGES = [('main.json', build_ss), ('home.json', build_home), ('settings.json', build_settings),
         ('brightness.json', build_brightness), ('video.json', build_video),
         ('album.json', build_album)]''', gen.strip(), 1)
open(p, 'w', encoding='utf-8').write(t)
print('gen_pages.py: + build_ssset()')

# ---------- ② sssetLogic.cc ----------
logic = r'''#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * sssetLogic.cc — 屏保显示子页（ssset.ftu）
 * 5 项显隐（时间/日期/温湿度/天气/设备状态条）存 /data：ss_item_<key> = 1/0。
 * 屏保页（mainLogic）按同一批键决定浮层显隐。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/StoragePreferences.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"

#include <stdio.h>
#include <string>

#define KEY_PREFIX "ss_item_"

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static const char* kKeys[5]   = { "time", "date", "temphum", "weather", "statusbar" };
static const char* kLabels[5] = { "时间", "日期", "温湿度", "天气", "设备状态条" };

static ZKTextView* chipBg(int i) {
    ZKTextView* a[5] = { mImageSsSetChip1Ptr, mImageSsSetChip2Ptr, mImageSsSetChip3Ptr,
                         mImageSsSetChip4Ptr, mImageSsSetChip5Ptr };
    return (i >= 0 && i < 5) ? a[i] : NULL;
}
static ZKTextView* chipTx(int i) {
    ZKTextView* a[5] = { mTextSsSetRowValue1Ptr, mTextSsSetRowValue2Ptr, mTextSsSetRowValue3Ptr,
                         mTextSsSetRowValue4Ptr, mTextSsSetRowValue5Ptr };
    return (i >= 0 && i < 5) ? a[i] : NULL;
}
static ZKButton* rowBtn(int i) {
    ZKButton* a[5] = { mButtonSsSetRow1Ptr, mButtonSsSetRow2Ptr, mButtonSsSetRow3Ptr,
                       mButtonSsSetRow4Ptr, mButtonSsSetRow5Ptr };
    return (i >= 0 && i < 5) ? a[i] : NULL;
}

static bool itemVisible(int i) {
    std::string k = std::string(KEY_PREFIX) + kKeys[i];
    return StoragePreferences::getInt(k, 1) != 0;      // 默认全显示
}

static void refreshRows() {
    for (int i = 0; i < 5; i++) {
        bool on = itemVisible(i);
        ZKTextView* bg = chipBg(i);
        ZKTextView* tx = chipTx(i);
        if (bg != NULL) bg->setBackgroundPic(on ? "images/chip68x44_hl.png" : "images/chip68x44.png");
        if (tx != NULL) {
            tx->setText(on ? "显示" : "隐藏");
            tx->setTextColor(on ? 0x10141A : 0xECECF0);
        }
    }
}

static void toggleRow(int i) {
    if (i < 0 || i > 4) return;
    std::string k = std::string(KEY_PREFIX) + kKeys[i];
    int next = itemVisible(i) ? 0 : 1;
    StoragePreferences::putInt(k, next);
    LOGD("ssset: %s -> %d", kKeys[i], next);
    refreshRows();
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextSsSetTitlePtr, mTextSsSetTitleEnPtr,
        mImageSsSetRowBg1Ptr, mImageSsSetRowBg2Ptr, mImageSsSetRowBg3Ptr,
        mImageSsSetRowBg4Ptr, mImageSsSetRowBg5Ptr,
        mTextSsSetRowLabel1Ptr, mTextSsSetRowLabel2Ptr, mTextSsSetRowLabel3Ptr,
        mTextSsSetRowLabel4Ptr, mTextSsSetRowLabel5Ptr,
        mImageSsSetChip1Ptr, mImageSsSetChip2Ptr, mImageSsSetChip3Ptr,
        mImageSsSetChip4Ptr, mImageSsSetChip5Ptr,
        mTextSsSetRowValue1Ptr, mTextSsSetRowValue2Ptr, mTextSsSetRowValue3Ptr,
        mTextSsSetRowValue4Ptr, mTextSsSetRowValue5Ptr,
        mTextSsSetHint1Ptr, mTextSsSetHint2Ptr,
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
    passDecorations();
    refreshRows();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }
static void onUI_show() { refreshRows(); }
static void onUI_hide() {}
static void onUI_quit() {}
static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }
static bool onUI_Timer(int id) { (void)id; return true; }
static bool onsssetActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonSsSetBack(ZKButton *p) {
    (void)p;
    EASYUICONTEXT->goBack();
    return true;
}
static bool onButtonClick_ButtonSsSetRow1(ZKButton *p) { (void)p; toggleRow(0); return true; }
static bool onButtonClick_ButtonSsSetRow2(ZKButton *p) { (void)p; toggleRow(1); return true; }
static bool onButtonClick_ButtonSsSetRow3(ZKButton *p) { (void)p; toggleRow(2); return true; }
static bool onButtonClick_ButtonSsSetRow4(ZKButton *p) { (void)p; toggleRow(3); return true; }
static bool onButtonClick_ButtonSsSetRow5(ZKButton *p) { (void)p; toggleRow(4); return true; }
'''
open(os.path.join(ROOT, 'src', 'logic', 'sssetLogic.cc'), 'w', encoding='utf-8').write(logic)
print('written src/logic/sssetLogic.cc')

# ---------- ③ 设置页接线：ButtonRowSsSet -> sssetActivity ----------
p = os.path.join(ROOT, 'src', 'logic', 'settingsLogic.cc')
t = open(p, encoding='utf-8').read()
import re
m = re.search(r'static bool onButtonClick_ButtonRowSsSet\(ZKButton \*pButton\) \{.*?\n\}', t, re.S)
if m:
    t = t[:m.start()] + ('static bool onButtonClick_ButtonRowSsSet(ZKButton *pButton) {\n'
                         '    (void)pButton;\n'
                         '    noteActivity();\n'
                         '    EASYUICONTEXT->openActivity("sssetActivity");\n'
                         '    return true;\n}') + t[m.end():]
    open(p, 'w', encoding='utf-8').write(t)
    print('settingsLogic: ButtonRowSsSet -> sssetActivity')
else:
    print('!! 未找到 ButtonRowSsSet 回调，需人工接线')
