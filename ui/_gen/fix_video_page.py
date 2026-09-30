# -*- coding: utf-8 -*-
"""修 video 页 3 个 check_all FAIL：①mainLogic 注释里的箭头 ②Int 回调名对齐 caption(1..6) ③间隔 chip 文案改短 + 素材列表套滚动窗。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if old not in t:
            print('!! MISS %s: %r' % (rel, old[:60]))
            continue
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', rel)


# ① 注释里的箭头（黑名单字符）
patch('src/logic/mainLogic.cc', [('\u2192 \u9000\u626b\u76ee\u5f55', '-> \u9000\u626b\u76ee\u5f55')])

# ② 回调名对齐 caption：ButtonVidInt1..6
patch('src/logic/videoLogic.cc', [
    ('static bool onButtonClick_ButtonVidInt0(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(0); }',
     'static bool onButtonClick_ButtonVidInt1(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(0); }'),
    ('static bool onButtonClick_ButtonVidInt1(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(1); }',
     'static bool onButtonClick_ButtonVidInt2(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(1); }'),
    ('static bool onButtonClick_ButtonVidInt2(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(2); }',
     'static bool onButtonClick_ButtonVidInt3(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(2); }'),
    ('static bool onButtonClick_ButtonVidInt3(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(3); }',
     'static bool onButtonClick_ButtonVidInt4(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(3); }'),
    ('static bool onButtonClick_ButtonVidInt4(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(4); }',
     'static bool onButtonClick_ButtonVidInt5(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(4); }'),
    ('static bool onButtonClick_ButtonVidInt5(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(5); }',
     'static bool onButtonClick_ButtonVidInt6(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(5); }'),
])

# ③ 间隔文案改短 + 素材列表套滚动窗（单内嵌 window，高=内容实际高）
patch('ui/_gen/gen_pages.py', [
    ("INT_LABELS = ['\u8fde\u7eed', '1\u5c0f\u65f6', '2\u5c0f\u65f6', '6\u5c0f\u65f6', '12\u5c0f\u65f6', '\u6bcf\u5929']",
     "INT_LABELS = ['\u8fde\u7eed', '1h', '2h', '6h', '12h', '\u6bcf\u5929']"),
    ("""    for i in range(VIDEO_ROWS):
        y = 92 + i * 42""",
     """    sc = scrollwin(r, 'ScrollVid', (0, 88, W, 330), drag=60, orientation=1, edge=1)
    inner = win(sc, 'WindowVidList', (0, 0, W, VIDEO_ROWS * 42 + 8), bg=-1, visible=True)
    for i in range(VIDEO_ROWS):
        y = i * 42"""),
    ("bgpic_layer(r, 'ImageVidRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')",
     "bgpic_layer(inner, 'ImageVidRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')"),
    ("btn(r, 'ButtonVidRow%d' % (i + 1), (14, y, 452, 38), '', C_TX, align=AL_LC)",
     "btn(inner, 'ButtonVidRow%d' % (i + 1), (14, y, 452, 38), '', C_TX, align=AL_LC)"),
    ("tv(r, 'TextVidRowName%d' % (i + 1), (34, y + 8, 340, 22), '', 18, C_TX, AL_LT)",
     "tv(inner, 'TextVidRowName%d' % (i + 1), (34, y + 8, 340, 22), '', 18, C_TX, AL_LT)"),
    ("tv(r, 'ImageVidRowChk%d' % (i + 1), (424, y + 9, 20, 20), '', 16, C_GN, AL_CC,",
     "tv(inner, 'ImageVidRowChk%d' % (i + 1), (424, y + 9, 20, 20), '', 16, C_GN, AL_CC,"),
    ("tv(r, 'TextVidIntLabel', (20, 604, 440, 24), '\u8f6e\u64ad\u95f4\u9694', 18, C_SUB, AL_LT)",
     "tv(r, 'TextVidIntLabel', (20, 426, 440, 24), '\u8f6e\u64ad\u95f4\u9694', 18, C_SUB, AL_LT)"),
    ("        x = 14 + i * 76\n        bgpic_layer(r, 'ImageVidIntBg%d' % (i + 1), (x, 632, 68, 44), 'images/chip68x44.png')\n        btn(r, 'ButtonVidInt%d' % (i + 1), (x, 632, 68, 44), '', C_TX, size=18)\n        tv(r, 'TextVidInt%d' % (i + 1), (x, 632, 68, 44), INT_LABELS[i], 18, C_TX, AL_CC)",
     "        x = 14 + i * 76\n        bgpic_layer(r, 'ImageVidIntBg%d' % (i + 1), (x, 452, 68, 44), 'images/chip68x44.png')\n        btn(r, 'ButtonVidInt%d' % (i + 1), (x, 452, 68, 44), '', C_TX, size=18)\n        tv(r, 'TextVidInt%d' % (i + 1), (x, 452, 68, 44), INT_LABELS[i], 18, C_TX, AL_CC)"),
])
