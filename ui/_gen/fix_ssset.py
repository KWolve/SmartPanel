# -*- coding: utf-8 -*-
"""修 ssset 页 check_all 三处 FAIL：
① settingsLogic 的 ButtonRowVideo 回调签名不规范（ZKButton* 无空格）+ 内容是 stub -> 规范签名 + 真接线
② ssset 行高 46 与图 srow452x38(452x38) 不一致 -> 行高 38，chip 上移 3px
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ① settingsLogic: ButtonRowVideo 规范化 + 接线
p = os.path.join(ROOT, 'src', 'logic', 'settingsLogic.cc')
t = open(p, encoding='utf-8').read()
m = re.search(r'static bool onButtonClick_ButtonRowVideo\(ZKButton\s*\*\s*pButton\)\s*\{.*?\n\}', t, re.S)
if m:
    new = ('static bool onButtonClick_ButtonRowVideo(ZKButton *pButton) {\n'
           '    (void)pButton;\n'
           '    noteActivity();\n'
           '    EASYUICONTEXT->openActivity("videoActivity");\n'
           '    return true;\n}')
    t = t[:m.start()] + new + t[m.end():]
    open(p, 'w', encoding='utf-8').write(t)
    print('settingsLogic: ButtonRowVideo 已规范化 + 接线 videoActivity')
else:
    print('!! ButtonRowVideo 回调未匹配')

# ② ssset 行高对齐图片 452x38
p = os.path.join(ROOT, 'ui', '_gen', 'gen_pages.py')
t = open(p, encoding='utf-8').read()
pairs = [
    ("bgpic_layer(r, 'ImageSsSetRowBg%d' % (i + 1), (14, y, 452, 46), 'images/srow452x38.png')",
     "bgpic_layer(r, 'ImageSsSetRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')"),
    ("btn(r, 'ButtonSsSetRow%d' % (i + 1), (14, y, 452, 46), '', C_TX, align=AL_LC)",
     "btn(r, 'ButtonSsSetRow%d' % (i + 1), (14, y, 452, 38), '', C_TX, align=AL_LC)"),
    ("tv(r, 'TextSsSetRowLabel%d' % (i + 1), (34, y + 12, 260, 22), label, 18, C_TX, AL_LT)",
     "tv(r, 'TextSsSetRowLabel%d' % (i + 1), (34, y + 8, 260, 22), label, 18, C_TX, AL_LT)"),
    ("bgpic_layer(r, 'ImageSsSetChip%d' % (i + 1), (378, y + 5, 68, 44), 'images/chip68x44.png')",
     "bgpic_layer(r, 'ImageSsSetChip%d' % (i + 1), (378, y - 3, 68, 44), 'images/chip68x44.png')"),
    ("tv(r, 'TextSsSetRowValue%d' % (i + 1), (378, y + 5, 68, 44), '显示', 18, C_TX, AL_CC)",
     "tv(r, 'TextSsSetRowValue%d' % (i + 1), (378, y - 3, 68, 44), '显示', 18, C_TX, AL_CC)"),
]
for a, b in pairs:
    if a in t:
        t = t.replace(a, b, 1)
    else:
        print('MISS gen_pages:', a[:60])
open(p, 'w', encoding='utf-8').write(t)
print('gen_pages.py: ssset 行高对齐完成')
