# -*- coding: utf-8 -*-
"""主页 3 个开关卡片也做高对比度效果（钟工 17:09）：
- 出 card_hl.png（绿底 #7BE0A3 + 圆角 16 + 1px 同色边）
- homeLogic.cc 接线：按下 / 开启 = 高对比（绿卡 + 深字）；关闭 = 常态卡 + 亮字
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
GN = (0x7B, 0xE0, 0xA3, 255)
SS = 4


def rounded(size, radius, fill):
    w, h = size
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill)
    return im.resize((w, h), Image.BOX)


out = os.path.join(IMGS, 'card_hl.png')
rounded((141, 216), 16, GN).save(out)
print('card_hl.png', os.path.getsize(out), 'B')

# ---- 接线 homeLogic.cc ----
p = os.path.join(ROOT, 'src', 'logic', 'homeLogic.cc')
t = open(p, encoding='utf-8').read()

helper = '''
static bool sDevOn[3] = { true, true, false };   // 业务接入后由 RelayManager 提供

static ZKTextView* devCardBg(int i) {
    ZKTextView* a[3] = { mImageCardBg1Ptr, mImageCardBg2Ptr, mImageCardBg3Ptr };
    return (i >= 0 && i < 3) ? a[i] : NULL;
}
static ZKTextView* devStateText(int i) {
    ZKTextView* a[3] = { mTextDevState1Ptr, mTextDevState2Ptr, mTextDevState3Ptr };
    return (i >= 0 && i < 3) ? a[i] : NULL;
}

// 高对比：开启 / 按下 = 绿卡 + 深字；关闭 = 常态卡 + 亮字
static void applyCardVisual(int i, bool highlight) {
    bool on = sDevOn[i] || highlight;
    ZKTextView* bg = devCardBg(i);
    ZKTextView* nm = devNameText(i);
    ZKTextView* st = devStateText(i);
    if (bg != NULL) bg->setBackgroundPic(on ? "images/card_hl.png" : "images/card.png");
    if (nm != NULL) nm->setTextColor(on ? CLR_CHIP_ON : C_TX);
    if (st != NULL) {
        st->setText(sDevOn[i] ? "开启" : "关闭");
        st->setTextColor(on ? CLR_CHIP_ON : C_DIM);
    }
}

static void refreshDevCards() {
    for (int i = 0; i < 3; i++) applyCardVisual(i, false);
}

class DevTouchListener : public ZKBase::ITouchListener {
public:
    explicit DevTouchListener(int idx) : mIdx(idx) {}
    virtual void onTouchEvent(ZKBase *pBase, const MotionEvent &ev) {
        (void)pBase;
        switch (ev.mActionStatus) {
        case MotionEvent::E_ACTION_DOWN:
            noteActivity();
            applyCardVisual(mIdx, true);
            break;
        case MotionEvent::E_ACTION_UP:
        case MotionEvent::E_ACTION_CANCEL:
            applyCardVisual(mIdx, false);
            break;
        default:
            break;
        }
    }
private:
    int mIdx;
};
static DevTouchListener sDevTouch1(0), sDevTouch2(1), sDevTouch3(2);

'''
anchor = '// 按下 高对比；抬起 回到「是否选中」的状态'
if anchor not in t:
    anchor = 'static void refreshDevNames() {'
assert anchor in t
t = t.replace(anchor, helper + anchor, 1)

t = t.replace('refreshDevNames();', 'refreshDevNames();\n    refreshDevCards();')

t = t.replace('    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setLongClickListener(&sDevLong1);',
              '    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setTouchListener(&sDevTouch1);\n'
              '    if (mButtonDev2Ptr != NULL) mButtonDev2Ptr->setTouchListener(&sDevTouch2);\n'
              '    if (mButtonDev3Ptr != NULL) mButtonDev3Ptr->setTouchListener(&sDevTouch3);\n'
              '    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setLongClickListener(&sDevLong1);', 1)

t = t.replace('    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setLongClickListener(NULL);',
              '    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setTouchListener(NULL);\n'
              '    if (mButtonDev2Ptr != NULL) mButtonDev2Ptr->setTouchListener(NULL);\n'
              '    if (mButtonDev3Ptr != NULL) mButtonDev3Ptr->setTouchListener(NULL);\n'
              '    if (mButtonDev1Ptr != NULL) mButtonDev1Ptr->setLongClickListener(NULL);', 1)

for i in (1, 2, 3):
    old = 'static bool onButtonClick_ButtonDev%d(ZKButton *pButton) { (void)pButton; noteActivity(); LOGD("relay %d toggle (业务待接)"); return true; }' % (i, i)
    old2 = 'static bool onButtonClick_ButtonDev%d(ZKButton *pButton) { (void)pButton; noteActivity(); LOGD("relay %d toggle"); return true; }' % (i, i)
    new = ('static bool onButtonClick_ButtonDev%d(ZKButton *pButton) {\n'
           '    (void)pButton;\n'
           '    noteActivity();\n'
           '    sDevOn[%d] = !sDevOn[%d];\n'
           '    applyCardVisual(%d, false);\n'
           '    LOGD("relay %d -> %%d (业务待接 RelayManager)", sDevOn[%d]);\n'
           '    return true;\n'
           '}') % (i, i - 1, i - 1, i - 1, i, i - 1)
    if old in t:
        t = t.replace(old, new, 1)
    elif old2 in t:
        t = t.replace(old2, new, 1)
    else:
        raise SystemExit('!! relay %d 回调未找到' % i)

open(p, 'w', encoding='utf-8').write(t)
print('homeLogic.cc patched')
