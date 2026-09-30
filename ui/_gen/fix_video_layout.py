# -*- coding: utf-8 -*-
"""屏保视频页：①间隔条被挤出屏幕 → 列表缩 30px、间隔区整体上移 ②空行连同底条一起隐藏（按实际条目显示）"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        assert old in t, 'MISS %s: %r' % (rel, old[:70])
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', rel)


# ---- ① 布局：列表 330→300，间隔标签/条上移 34px（452+44=496 > 480 溢出）
patch('ui/_gen/gen_pages.py', [
    ("scrollwin(r, 'ScrollVid', (0, 88, W, 330), drag=60, orientation=1, edge=1)",
     "scrollwin(r, 'ScrollVid', (0, 88, W, 300), drag=60, orientation=1, edge=1)"),
    ("tv(r, 'TextVidIntLabel', (20, 426, 440, 24), '\u8f6e\u64ad\u95f4\u9694', 18, C_SUB, AL_LT)",
     "tv(r, 'TextVidIntLabel', (20, 398, 440, 24), '\u8f6e\u64ad\u95f4\u9694', 18, C_SUB, AL_LT)"),
    ("bgpic_layer(r, 'ImageVidIntBg%d' % (i + 1), (x, 452, 68, 44), 'images/chip68x44.png')",
     "bgpic_layer(r, 'ImageVidIntBg%d' % (i + 1), (x, 424, 68, 44), 'images/chip68x44.png')"),
    ("btn(r, 'ButtonVidInt%d' % (i + 1), (x, 452, 68, 44), '', C_TX, size=18)",
     "btn(r, 'ButtonVidInt%d' % (i + 1), (x, 424, 68, 44), '', C_TX, size=18)"),
    ("tv(r, 'TextVidInt%d' % (i + 1), (x, 452, 68, 44), INT_LABELS[i], 18, C_TX, AL_CC)",
     "tv(r, 'TextVidInt%d' % (i + 1), (x, 424, 68, 44), INT_LABELS[i], 18, C_TX, AL_CC)"),
])

# ---- ② videoLogic：空行的底条也要隐藏（原来只藏了名字/勾/按钮，底条留着 → 看着像空条目）
patch('src/logic/videoLogic.cc', [
    ("static ZKTextView* intBg(int i) {",
     """static ZKTextView* rowBg(int i) {
    ZKTextView* a[MAX_ROWS] = { mImageVidRowBg1Ptr, mImageVidRowBg2Ptr, mImageVidRowBg3Ptr, mImageVidRowBg4Ptr,
                                mImageVidRowBg5Ptr, mImageVidRowBg6Ptr, mImageVidRowBg7Ptr, mImageVidRowBg8Ptr,
                                mImageVidRowBg9Ptr, mImageVidRowBg10Ptr, mImageVidRowBg11Ptr, mImageVidRowBg12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}
static ZKTextView* intBg(int i) {"""),
    ("""        ZKButton* b = rowBtn(i);
        ZKTextView* n = rowName(i);
        ZKTextView* c = rowChk(i);
        bool has = i < (int)sFiles.size();
        if (b != NULL) b->setVisible(has);""",
     """        ZKButton* b = rowBtn(i);
        ZKTextView* n = rowName(i);
        ZKTextView* c = rowChk(i);
        ZKTextView* g = rowBg(i);
        bool has = i < (int)sFiles.size();
        if (b != NULL) b->setVisible(has);
        if (g != NULL) g->setVisible(has);      // 空行连同底条一起藏：列表只显示实际条目"""),
])
