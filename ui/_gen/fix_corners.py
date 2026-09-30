# -*- coding: utf-8 -*-
"""修弹窗按键「倒角异常」：把 .9.png 换成**固定尺寸**图（圆角由图形本身保证，不被 9-patch 拉伸/marker 环破坏）。
覆盖：重命名框(368x200) / 情景编辑框(344x200) / 确定&取消(152x44) / 情景编辑保存(308x46) /
      亮度保存(440x48) / 情景灯chip(96x40) / 设置行(452x50) / 图标底(34x34) / 屏保状态芯片(141x40)
"""
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
SS = 4
SF = (0x26, 0x26, 0x2E, 255)
IC = (0x31, 0x31, 0x3A, 255)
GN = (0x7B, 0xE0, 0xA3, 255)
SSCHIP = (38, 38, 46, 224)      # rgba(38,38,46,.88)


def rounded(w, h, radius, fill, border=None, bw=1):
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if border is not None:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=border)
        i = bw * SS
        d.rounded_rectangle([i, i, w * SS - 1 - i, h * SS - 1 - i],
                            radius=max(0, (radius - bw) * SS), fill=fill)
    else:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill)
    return im.resize((w, h), Image.BOX)


ASSETS = [
    ('mbox368.png', rounded(368, 200, 20, SF)),
    ('mbox344.png', rounded(344, 200, 20, SF)),
    ('btn_primary152x44.png', rounded(152, 44, 12, GN)),
    ('btn_primary308x46.png', rounded(308, 46, 12, GN)),
    ('btn_primary440x48.png', rounded(440, 48, 12, GN)),
    ('msw96x40.png', rounded(96, 40, 12, IC)),
    ('msw152x44.png', rounded(152, 44, 12, IC)),
    ('srow452x50.png', rounded(452, 50, 12, SF)),
    ('sicon34x34.png', rounded(34, 34, 10, IC)),
    ('sschip141x40.png', rounded(141, 40, 12, SSCHIP)),
]
for name, im in ASSETS:
    p = os.path.join(IMGS, name)
    im.save(p)
    print('%-24s %s %5d B' % (name, im.size, os.path.getsize(p)))

# ---- 改引用（按上下文精确替换）----
p = os.path.join(ROOT, 'ui', '_gen', 'gen_pages.py')
t = open(p, encoding='utf-8').read()
reps = [
    ("bgpic_layer(md, 'ImageMbox', (68, 120, 344, 200), 'images/mbox.9.png')",
     "bgpic_layer(md, 'ImageMbox', (68, 120, 344, 200), 'images/mbox344.png')"),
    ("bgpic_layer(rn, 'ImageRenameBox', (56, 130, 368, 200), 'images/mbox.9.png')",
     "bgpic_layer(rn, 'ImageRenameBox', (56, 130, 368, 200), 'images/mbox368.png')"),
    ("bgpic_layer(md, 'ImageEditSaveBg', (86, 258, 308, 46), 'images/btn_primary.9.png')",
     "bgpic_layer(md, 'ImageEditSaveBg', (86, 258, 308, 46), 'images/btn_primary308x46.png')"),
    ("bgpic_layer(rn, 'ImageRenameOkBg', (76, 272, 152, 44), 'images/btn_primary.9.png')",
     "bgpic_layer(rn, 'ImageRenameOkBg', (76, 272, 152, 44), 'images/btn_primary152x44.png')"),
    ("bgpic_layer(rn, 'ImageRenameCancelBg', (252, 272, 152, 44), 'images/msw.9.png')",
     "bgpic_layer(rn, 'ImageRenameCancelBg', (252, 272, 152, 44), 'images/msw152x44.png')"),
    ("bgpic_layer(r, 'ImageBrSaveBg', (20, 366, 440, 48), 'images/btn_primary.9.png')",
     "bgpic_layer(r, 'ImageBrSaveBg', (20, 366, 440, 48), 'images/btn_primary440x48.png')"),
    ("bgpic_layer(inner, cap + 'Bg', (ROW_X, y, ROW_W, ROW_H), 'images/srow.9.png')",
     "bgpic_layer(inner, cap + 'Bg', (ROW_X, y, ROW_W, ROW_H), 'images/srow452x50.png')"),
    ("bgpic='images/sicon.9.png')", "bgpic='images/sicon34x34.png')"),
    ("bgpic_layer(r, 'ImageSsChip%d' % (i + 1), (x, 396, 141, 40), 'images/ss_chip.9.png')",
     "bgpic_layer(r, 'ImageSsChip%d' % (i + 1), (x, 396, 141, 40), 'images/sschip141x40.png')"),
]
for old, new in reps:
    if old in t:
        t = t.replace(old, new, 1)
    else:
        print('!! MISS:', old[:64])
# 情景编辑 3 个灯 chip（96x40 固定图）
t = t.replace("bgpic_layer(md, 'ImageMswBg%d' % (i + 1), (x, 204, 96, 40), 'images/msw.9.png')",
              "bgpic_layer(md, 'ImageMswBg%d' % (i + 1), (x, 204, 96, 40), 'images/msw96x40.png')")
open(p, 'w', encoding='utf-8').write(t)
print('gen_pages.py 引用已改')
