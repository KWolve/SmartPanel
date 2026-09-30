# -*- coding: utf-8 -*-
"""钟工 2026-09-29 14:58 四条设置口径的落地脚本

1) 入口位置：放设置页「屏保显示」下 —— 已做，无需改（这里只做断言）
2) 尺寸：只有 1 个开关时更大 —— 卡片宽 **460**（x=10，居中）
3) 名字修改：在「按键配置」页里复用重命名弹窗（克隆主页 WindowRename 那套）
4) 文案：相册页二维码文案 → 「微信扫一扫，打开小程序」
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')

# ── ② 主页：1 个开关时卡片宽 460 ──────────────────────────────
lp = os.path.join(ROOT, 'src', 'logic', 'homeLogic.cc')
t = io.open(lp, encoding='utf-8').read()
old = "    int w = (n >= 3) ? 141 : (n == 2 ? 216 : 260);"
new = ("    // 尺寸口径（钟工 2026-09-29 14:58）：3 个 = 141（原布局）、2 个 = 216、\n"
       "    //   1 个 = **460**（几乎满宽，画面更饱满）\n"
       "    int w = (n >= 3) ? 141 : (n == 2 ? 216 : 460);")
assert old in t, '未找到宽度公式'
t = t.replace(old, new, 1)
io.open(lp, 'w', encoding='utf-8').write(t)
print('② homeLogic.cc：1 个开关 -> 卡片宽 460（x=10 居中）')

# ── ④ 相册页二维码文案 ────────────────────────────────────────
ap = os.path.join(UI, 'album.json')
al = json.load(io.open(ap, encoding='utf-8'))
hit = []


def patch(o):
    if isinstance(o, dict):
        if o.get('caption') == 'TextAlQrCap':
            o['text'] = '微信扫一扫，打开小程序'
            hit.append(o.get('text'))
        for v in o.values():
            patch(v)
    elif isinstance(o, list):
        for v in o:
            patch(v)


patch(al)
assert hit == ['微信扫一扫，打开小程序'], hit
# 宽度 200 -> 280（新文案 10 字，20px 字号需要更宽，仍居中在卡片下方）
def widen(o):
    if isinstance(o, dict):
        if o.get('caption') == 'TextAlQrCap':
            o['position'] = dict(o['position'], left=100, width=280)
        for v in o.values():
            widen(v)
    elif isinstance(o, list):
        for v in o:
            widen(v)


widen(al)
json.dump(al, io.open(ap, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('④ album.json：TextAlQrCap -> 微信扫一扫，打开小程序（框 100..380 居中）')

# ── ③ keyset 页：加「改名」入口（复用重命名弹窗）────────────────
kp = os.path.join(UI, 'keyset.json')
ks = json.load(io.open(kp, encoding='utf-8'))
hm = json.load(io.open(os.path.join(UI, 'home.json'), encoding='utf-8'))
rename_win = json.loads(json.dumps(hm['window__3']))
assert rename_win['caption'] == 'WindowRename', rename_win.get('caption')

# 克隆窗口内的控件，继续按类型编号
tv_max = max(int(re.findall(r'\d+', k)[0]) for k in ks if k.startswith('textview__'))
bt_max = max(int(re.findall(r'\d+', k)[0]) for k in ks if k.startswith('button__'))
tv_max += 1
bt_max += 1
kids = {}
for k, v in rename_win.items():
    if k.startswith('textview__'):
        kids['textview__%d' % tv_max] = v
        tv_max += 1
    elif k.startswith('button__'):
        kids['button__%d' % bt_max] = v
        bt_max += 1
    elif k.startswith('edittext__'):
        kids['edittext__1'] = v
rename_win = {k: v for k, v in rename_win.items() if not re.match(r'^(textview|button|edittext)__\d+$', k)}
rename_win.update(kids)
rename_win['visible'] = False
ks['window__1'] = rename_win

# 每行名字区加一个按钮（点名字 -> 改名；行内其它位置仍是切显示/隐藏）
for i in range(3):
    y = 84 + i * 52
    b = json.loads(json.dumps(ks['button__%d' % (i + 2)]))     # 克隆 ButtonKsRowN（同款空按钮）
    b['caption'] = 'ButtonKsName%d' % (i + 1)
    bt_max += 1
    b['id'] = 20000 + bt_max
    b['position'] = {'left': 30, 'top': y + 4, 'width': 268, 'height': 38}
    ks['button__%d' % bt_max] = b
for k, v in ks.items():
    if isinstance(v, dict) and v.get('caption') == 'TextKsHint3':
        v['text'] = '点名字 = 改名（复用重命名弹窗）；点行内其它位置 = 切换显示/隐藏'
json.dump(ks, io.open(kp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('③ keyset.json：+ WindowRename 弹窗 + ButtonKsName1..3 + 提示文案')

# ── ③ keysetLogic.cc：改名逻辑（与主页同一套 ConfigStore::setRelayName）──
logic = r'''#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * keysetLogic.cc - 按键配置子页（keyset.ftu）
 * 主页 3 个开关（继电器 1..3）的显隐：存 /data: sw_show_1..3 = 1/0（默认显示）。
 * 主页 homeLogic 按同一批键决定卡片显隐 + 自动重排（1/2/3 个按键的尺寸/布局）。
 * 界面照「屏保显示」(ssset)：左名字 + 右侧「显示/隐藏」chip，点整行切换。
 * 改名（钟工 2026-09-29 14:58）：点名字 -> 复用主页那套重命名弹窗（WindowRename），
 *   落盘仍是 ConfigStore::setRelayName()（与主页长按改名同一份数据、同一份截断规则）。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"
#include "control/ZKEditText.h"
#include "window/ZKWindow.h"
#include "network/MqttBridge.h"

#include <stdio.h>
#include <string>

#define CH_N 3
#define SW_KEY_PREFIX "sw_show_"

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static int sRenameCh = 1;                     // 正在改名的通道（1..3）

static ZKTextView* chipBg(int i) {
    ZKTextView* a[CH_N] = { mImageKsChip1Ptr, mImageKsChip2Ptr, mImageKsChip3Ptr };
    return (i >= 0 && i < CH_N) ? a[i] : NULL;
}
static ZKTextView* chipTx(int i) {
    ZKTextView* a[CH_N] = { mTextKsRowValue1Ptr, mTextKsRowValue2Ptr, mTextKsRowValue3Ptr };
    return (i >= 0 && i < CH_N) ? a[i] : NULL;
}
static ZKTextView* rowLabel(int i) {
    ZKTextView* a[CH_N] = { mTextKsRowLabel1Ptr, mTextKsRowLabel2Ptr, mTextKsRowLabel3Ptr };
    return (i >= 0 && i < CH_N) ? a[i] : NULL;
}
static ZKButton* rowBtn(int i) {
    ZKButton* a[CH_N] = { mButtonKsRow1Ptr, mButtonKsRow2Ptr, mButtonKsRow3Ptr };
    return (i >= 0 && i < CH_N) ? a[i] : NULL;
}

static std::string swKey(int i) {
    char b[32];
    snprintf(b, sizeof(b), SW_KEY_PREFIX "%d", i + 1);
    return std::string(b);
}

// 主页/本页同一口径：默认显示
static bool swVisible(int i) {
    return StoragePreferences::getInt(swKey(i), 1) != 0;
}

static void refreshRows() {
    ConfigStore* cfg = ConfigStore::getInstance();
    for (int i = 0; i < CH_N; i++) {
        ZKTextView* lb = rowLabel(i);
        ZKTextView* bg = chipBg(i);
        ZKTextView* tx = chipTx(i);
        if (lb != NULL) lb->setText(cfg->relayName(i + 1).c_str());
        bool on = swVisible(i);
        if (bg != NULL) bg->setBackgroundPic(on ? "images/chip68x44_hl.png" : "images/chip68x44.png");
        if (tx != NULL) {
            tx->setText(on ? "显示" : "隐藏");
            tx->setTextColor(on ? 0x10141A : 0xECECF0);
        }
    }
}

static int visibleCount() {
    int n = 0;
    for (int i = 0; i < CH_N; i++) if (swVisible(i)) n++;
    return n;
}

static void toggleRow(int i) {
    if (i < 0 || i >= CH_N) return;
    int next = swVisible(i) ? 0 : 1;
    if (next == 0 && visibleCount() <= 1) {          // 至少留一个，避免主页空屏
        LOGD("keyset: 至少保留 1 个按键显示，忽略本次隐藏");
        return;
    }
    StoragePreferences::putInt(swKey(i), next);
    LOGD("keyset: %s -> %d", swKey(i).c_str(), next);
    refreshRows();
}

// 改名：复用主页那套弹窗（WindowRename），落盘同一份 relayName
static void openRename(int ch) {
    sRenameCh = ch;
    if (mWindowRenamePtr == NULL) return;
    std::string cur = ConfigStore::getInstance()->relayName(ch);
    if (mEditRenamePtr != NULL) mEditRenamePtr->setText(cur.c_str());
    mWindowRenamePtr->showWnd();
    LOGD("keyset: rename dialog ch%d (cur=%s)", ch, cur.c_str());
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextKsTitlePtr, mTextKsTitleEnPtr,
        mImageKsRowBg1Ptr, mImageKsRowBg2Ptr, mImageKsRowBg3Ptr,
        mTextKsRowLabel1Ptr, mTextKsRowLabel2Ptr, mTextKsRowLabel3Ptr,
        mImageKsChip1Ptr, mImageKsChip2Ptr, mImageKsChip3Ptr,
        mTextKsRowValue1Ptr, mTextKsRowValue2Ptr, mTextKsRowValue3Ptr,
        mTextKsHint1Ptr, mTextKsHint2Ptr, mTextKsHint3Ptr,
        // 重命名弹窗的装饰层（弹窗内的按钮在上面，装饰件不得吃点击）
        mImageRenameDimPtr, mImageRenameBoxPtr, mTextRenameTitlePtr, mTextRenameHintPtr,
        mImageRenameOkBgPtr, mImageRenameCancelBgPtr,
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
static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保
    if (mWindowRenamePtr != NULL) mWindowRenamePtr->hideWnd();
    refreshRows();
}
static void onUI_hide() {}
static void onUI_quit() {}
static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }
static bool onUI_Timer(int id) { (void)id; return true; }
static bool onkeysetActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonKsBack(ZKButton *p) {
    (void)p;
    EASYUICONTEXT->goBack();
    return true;
}
static bool onButtonClick_ButtonKsRow1(ZKButton *p) { (void)p; toggleRow(0); return true; }
static bool onButtonClick_ButtonKsRow2(ZKButton *p) { (void)p; toggleRow(1); return true; }
static bool onButtonClick_ButtonKsRow3(ZKButton *p) { (void)p; toggleRow(2); return true; }
static bool onButtonClick_ButtonKsName1(ZKButton *p) { (void)p; openRename(1); return true; }
static bool onButtonClick_ButtonKsName2(ZKButton *p) { (void)p; openRename(2); return true; }
static bool onButtonClick_ButtonKsName3(ZKButton *p) { (void)p; openRename(3); return true; }

// 确定 -> 落盘 + 刷新本页行名（截断规则与主页一致：UTF-8 安全截到 kMaxNameBytes）
static bool onButtonClick_ButtonRenameOk(ZKButton *pButton) {
    (void)pButton;
    if (mEditRenamePtr != NULL) {
        std::string name = mEditRenamePtr->getText();
        size_t b = name.find_first_not_of(" \t\r\n");
        size_t e = name.find_last_not_of(" \t\r\n");
        name = (b == std::string::npos) ? "" : name.substr(b, e - b + 1);
        std::string out;
        for (size_t i = 0; i < name.size() && out.size() < (size_t)ConfigStore::kMaxNameBytes;) {
            unsigned char c = (unsigned char)name[i];
            size_t len = (c < 0x80) ? 1 : ((c >> 5) == 0x6 ? 2 : ((c >> 4) == 0xE ? 3 : 4));
            if (i + len > name.size()) break;
            out.append(name, i, len);
            i += len;
        }
        if (!out.empty()) {
            ConfigStore::getInstance()->setRelayName(sRenameCh, out);
            refreshRows();
            MqttBridge::getInstance()->republishDiscovery();   // 名字变了 -> 重发 HA discovery
            LOGD("keyset: rename ch%d -> %s", sRenameCh, out.c_str());
        }
    }
    if (mWindowRenamePtr != NULL) mWindowRenamePtr->hideWnd();
    return true;
}

static bool onButtonClick_ButtonRenameCancel(ZKButton *pButton) {
    (void)pButton;
    if (mWindowRenamePtr != NULL) mWindowRenamePtr->hideWnd();
    return true;
}

static void onEditTextChanged_EditRename(const std::string &text) {
    LOGD("keyset rename input: %s", text.c_str());
}
'''
io.open(os.path.join(ROOT, 'src', 'logic', 'keysetLogic.cc'), 'w',
        encoding='utf-8').write(logic)
print('③ keysetLogic.cc：改名逻辑 + 名字点按回调 已写入')
print('\n接下来：cd ui && fui.exe pack ./ ；再 fun.exe build -p Z20 ；再 fun.exe pack -p Z20 --release-version 1.56')
