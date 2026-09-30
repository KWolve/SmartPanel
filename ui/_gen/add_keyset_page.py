# -*- coding: utf-8 -*-
"""按键配置子页（keyset）：主页 3 个开关（继电器）的显隐配置，界面照「屏保显示」(ssset) 的效果。

做四件事：
 ① ui/keyset.json   —— 3 行（开关名 + 右侧 显示/隐藏 chip），克隆 ssset 的控件样式与资源
 ② ui/settings.json —— 设置页「屏保显示」下面插一行「按键配置」（下方各行整体下移 56，列表高度 +56）
 ③ src/logic/keysetLogic.cc —— 3 行切换（存 /data：sw_show_1..3，默认显示；名字取 ConfigStore::relayName）
 ④ src/logic/settingsLogic.cc —— 接线：行 → keysetActivity；行值刷新；装饰层放行触摸
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')

ROW_N = 3
KEY_PREFIX = 'sw_show_'

# ── ① keyset.json（克隆 ssset.json 的样式）──────────────────────────
ss = json.load(io.open(os.path.join(UI, 'ssset.json'), encoding='utf-8'))
by_cap = {}
for k, v in ss.items():
    if isinstance(v, dict) and 'caption' in v:
        by_cap[v['caption']] = v


def cp(cap):
    return json.loads(json.dumps(by_cap[cap]))          # 深拷贝


ks = {k: json.loads(json.dumps(v)) for k, v in ss.items()
      if not isinstance(v, dict) or 'caption' not in v}          # 根字段
ks.pop('textview__1', None)
for k in list(ks.keys()):
    if re.match(r'^(textview|button|window|scrollwindow)__\d+$', k):
        ks.pop(k)

tv_n = [0]
btn_n = [0]


def add_text(cap, src_cap, left, top, w, h, text=None, font=None):
    c = cp(src_cap)
    c['caption'] = cap
    tv_n[0] += 1
    c['id'] = 50000 + tv_n[0]
    c['position'] = {'left': left, 'top': top, 'width': w, 'height': h}
    if text is not None:
        c['text'] = text
    if font is not None:
        c['fontSize'] = font
    ks['textview__%d' % tv_n[0]] = c
    return c


def add_button(cap, src_cap, left, top, w, h):
    c = cp(src_cap)
    c['caption'] = cap
    btn_n[0] += 1
    c['id'] = 20000 + btn_n[0]
    c['position'] = {'left': left, 'top': top, 'width': w, 'height': h}
    ks['button__%d' % btn_n[0]] = c
    return c


add_text('TextKsTitle', 'TextSsSetTitle', 20, 12, 260, 30, '按键配置')
add_text('TextKsTitleEn', 'TextSsSetTitleEn', 20, 44, 300, 22, 'PANEL SWITCHES')
add_button('ButtonKsBack', 'ButtonSsSetBack', 372, 16, 90, 32)

for i in range(ROW_N):
    y = 84 + i * 52
    add_text('ImageKsRowBg%d' % (i + 1), 'ImageSsSetRowBg1', 14, y, 452, 46)
    add_text('TextKsRowLabel%d' % (i + 1), 'TextSsSetRowLabel1', 34, y + 12, 260, 22,
             '开关%d' % (i + 1))
    add_text('ImageKsChip%d' % (i + 1), 'ImageSsSetChip1', 378, y + 5, 68, 44)
    add_button('ButtonKsRow%d' % (i + 1), 'ButtonSsSetRow1', 14, y, 452, 46)
    add_text('TextKsRowValue%d' % (i + 1), 'TextSsSetRowValue1', 378, y + 5, 68, 44, '显示')

add_text('TextKsHint1', 'TextSsSetHint1', 20, 290, 440, 22,
         '点行切换「显示 / 隐藏」（立即生效并存 /data）')
add_text('TextKsHint2', 'TextSsSetHint2', 20, 316, 440, 22,
         '隐藏后主页按键自动放大重排（1 / 2 / 3 个都居中协调）')
add_text('TextKsHint3', 'TextSsSetHint2', 20, 342, 440, 22,
         '改名字：在主页长按对应按键')

# 控件数排序：textview__N / button__N 连续编号已满足（add_* 顺序分配）
json.dump(ks, io.open(os.path.join(UI, 'keyset.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('① 写出 ui/keyset.json（%d 控件）' % (tv_n[0] + btn_n[0]))

# ── ② settings.json：插一行「按键配置」───────────────────────────────
sp = os.path.join(UI, 'settings.json')
st = json.load(io.open(sp, encoding='utf-8'))
win = st['scrollwindow__1']['window__1']
ssset_rows = {v['caption']: v for k, v in win.items()
              if isinstance(v, dict) and str(v.get('caption', '')).startswith('ButtonRowSsSet')}
assert len(ssset_rows) == 7, sorted(ssset_rows)
INSERT_TOP, SHIFT = 396, 56


def ren(cap, src_cap, top=None, text=None, pic=None):
    c = json.loads(json.dumps(ssset_rows[src_cap]))
    c['caption'] = cap
    if top is not None:
        c['position'] = dict(c['position'], top=top)
    if text is not None:
        c['text'] = text
    if pic is not None:
        c['backgroundPic'] = pic
    return c


# 下方各行整体下移
moved = 0
for k, v in win.items():
    if isinstance(v, dict) and isinstance(v.get('position'), dict) and v.get('position', {}).get('top', -1) >= INSERT_TOP:
        v['position']['top'] += SHIFT
        moved += 1
win['position']['height'] += SHIFT                      # 列表内容高度 776 -> 832
print('② 设置页下移 %d 个控件；列表高度 -> %d' % (moved, win['position']['height']))

# id 分配（设置页现有最大：textview 50540 / button 20152）
new_tv_id, new_btn_id = 50541, 20160
for cap, src, dx, dy, kind in (
        ('ButtonRowKeySetBg', 'ButtonRowSsSetBg', 0, 0, 'tv'),
        ('ButtonRowKeySet', 'ButtonRowSsSet', 0, 0, 'btn'),
        ('ButtonRowKeySetIconBg', 'ButtonRowSsSetIconBg', 0, 0, 'tv'),
        ('ButtonRowKeySetIcon', 'ButtonRowSsSetIcon', 0, 0, 'tv'),
        ('ButtonRowKeySetLabel', 'ButtonRowSsSetLabel', 0, 0, 'tv'),
        ('ButtonRowKeySetValue', 'ButtonRowSsSetValue', 0, 0, 'tv'),
        ('ButtonRowKeySetChevron', 'ButtonRowSsSetChevron', 0, 0, 'tv')):
    c = ren(cap, src, top=INSERT_TOP + dy)
    if cap == 'ButtonRowKeySetLabel':
        c['text'] = '按键配置'
    elif cap == 'ButtonRowKeySetValue':
        c['text'] = '3 个显示 - 可增删'
    elif cap == 'ButtonRowKeySetIcon':
        c['backgroundPic'] = 'images/ic_sliders_g20.png'
    if cap == 'ButtonRowKeySet':
        c['id'] = new_btn_id
        win['button__%d' % (max(int(re.findall(r'\d+', k)[0]) for k in win if k.startswith('button__')) + 1)] = c
    else:
        c['id'] = new_tv_id
        new_tv_id += 1
        win['textview__%d' % (max(int(re.findall(r'\d+', k)[0]) for k in win if k.startswith('textview__')) + 1)] = c
json.dump(st, io.open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('② 已插入「按键配置」行（id 50541-50546 / 20160）')

# ── ③ keysetLogic.cc ────────────────────────────────────────────────
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
 * 名字 = ConfigStore::relayName(i+1)（主页长按可改）。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"

#include <stdio.h>
#include <string>

#define CH_N 3
#define SW_KEY_PREFIX "sw_show_"

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

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

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextKsTitlePtr, mTextKsTitleEnPtr,
        mImageKsRowBg1Ptr, mImageKsRowBg2Ptr, mImageKsRowBg3Ptr,
        mTextKsRowLabel1Ptr, mTextKsRowLabel2Ptr, mTextKsRowLabel3Ptr,
        mImageKsChip1Ptr, mImageKsChip2Ptr, mImageKsChip3Ptr,
        mTextKsRowValue1Ptr, mTextKsRowValue2Ptr, mTextKsRowValue3Ptr,
        mTextKsHint1Ptr, mTextKsHint2Ptr, mTextKsHint3Ptr,
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
'''
io.open(os.path.join(ROOT, 'src', 'logic', 'keysetLogic.cc'), 'w',
        encoding='utf-8').write(logic)
print('③ 写出 src/logic/keysetLogic.cc')

# ── ④ settingsLogic.cc：接线 + 行值 + 装饰放行 ────────────────────────
lp = os.path.join(ROOT, 'src', 'logic', 'settingsLogic.cc')
t = io.open(lp, encoding='utf-8').read()

# ④a 装饰层放行
anchor = ('        mButtonRowAlbumBgPtr, mButtonRowAlbumIconBgPtr, mButtonRowAlbumIconPtr, '
          'mButtonRowAlbumLabelPtr, mButtonRowAlbumValuePtr, mButtonRowAlbumChevronPtr,\n')
assert anchor in t
if 'mButtonRowKeySetBgPtr' not in t:
    t = t.replace(anchor, anchor +
                  '        // 按键配置行（钟工 2026-09-29）：同坑——整行要能点，装饰层必须放行\n'
                  '        mButtonRowKeySetBgPtr, mButtonRowKeySetIconBgPtr, mButtonRowKeySetIconPtr,\n'
                  '        mButtonRowKeySetLabelPtr, mButtonRowKeySetValuePtr, mButtonRowKeySetChevronPtr,\n', 1)

# ④b 行值刷新（插在屏保显示行之后）
a2 = '''        snprintf(b, sizeof(b), "%d 项开启 - 可增删", on);
        mButtonRowSsSetValuePtr->setText(b);
    }
'''
assert a2 in t
if 'mButtonRowKeySetValuePtr' not in t.split('static bool onButtonClick')[0]:
    t = t.replace(a2, a2 + '''
    // 按键配置行（钟工 2026-09-29）：显示几个开关（存 /data: sw_show_1..3，主页按同批键重排）
    if (mButtonRowKeySetValuePtr != NULL) {
        int on = 0;
        for (int i = 1; i <= 3; i++) {
            char k[32];
            snprintf(k, sizeof(k), "sw_show_%d", i);
            if (StoragePreferences::getInt(k, 1) != 0) on++;
        }
        snprintf(b, sizeof(b), "%d 个显示 - 可增删", on);
        mButtonRowKeySetValuePtr->setText(b);
    }
''', 1)

# ④c 回调
m = re.search(r'static bool onButtonClick_ButtonRowSsSet\(ZKButton \*pButton\) \{.*?\n\}', t, re.S)
assert m, '未找到 ButtonRowSsSet 回调'
if 'onButtonClick_ButtonRowKeySet' not in t:
    ins = ('''

static bool onButtonClick_ButtonRowKeySet(ZKButton *pButton) {
    (void)pButton;
    noteActivity();
    EASYUICONTEXT->openActivity("keysetActivity");
    return true;
}''')
    t = t[:m.end()] + ins + t[m.end():]
io.open(lp, 'w', encoding='utf-8').write(t)
print('④ settingsLogic.cc 已接线（放行/行值/回调）')
print('\n完成。接下来：cd ui && fui.exe pack ./  然后 fun.exe build -p Z20')
