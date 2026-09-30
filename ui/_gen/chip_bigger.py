# -*- coding: utf-8 -*-
"""主页情景 chip 改大：宽度 100 / 高度 60（钟工 17:17）。"""
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
SS = 4
SF = (0x26, 0x26, 0x2E, 255)
BD = (0x31, 0x31, 0x3A, 255)
GN = (0x7B, 0xE0, 0xA3, 255)


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


for name, im in (('chip.png', rounded(100, 60, 30, SF, BD)),
                 ('chip_hl.png', rounded(100, 60, 30, GN)),
                 ('chip_on.png', rounded(100, 60, 30, GN))):
    p = os.path.join(IMGS, name)
    im.save(p)
    print('%-14s %s %d B' % (name, im.size, os.path.getsize(p)))

# gen_borders.py 里的尺寸同步（下次重跑不回落）
gb = os.path.join(ROOT, 'ui', '_gen', 'gen_borders.py')
t = open(gb, encoding='utf-8').read()
t = t.replace("save(pill_or_round((84, 44), 22, SF, BD), 'chip.png')",
              "save(pill_or_round((100, 60), 30, SF, BD), 'chip.png')")
t = t.replace("save(pill_or_round((84, 44), 22, GN), 'chip_on.png')",
              "save(pill_or_round((100, 60), 30, GN), 'chip_on.png')")
t = t.replace("save(pill_or_round((84, 44), 22, GN), 'chip_hl.png')",
              "save(pill_or_round((100, 60), 30, GN), 'chip_hl.png')")
open(gb, 'w', encoding='utf-8').write(t)

# gen_pages.py：chip 尺寸/步进 + 滑动窗高度
gp = os.path.join(ROOT, 'ui', '_gen', 'gen_pages.py')
t = open(gp, encoding='utf-8').read()
t = t.replace("CHIP_W, CHIP_STEP, CHIP_X0 = 84, 96, 16", "CHIP_W, CHIP_STEP, CHIP_X0 = 100, 108, 16")
t = t.replace("strip = win(r, 'WindowSceneStrip', (0, 392, W, 44), bg=-1, visible=True)",
              "strip = win(r, 'WindowSceneStrip', (0, 388, W, 60), bg=-1, visible=True)")
t = t.replace("bgpic_layer(strip, 'ImageChipBg%d' % (i + 1), (cx, 0, CHIP_W, 44), 'images/chip.png', vis)",
              "bgpic_layer(strip, 'ImageChipBg%d' % (i + 1), (cx, 0, CHIP_W, 60), 'images/chip.png', vis)")
t = t.replace("btn(strip, 'ButtonSceneChip%d' % (i + 1), (cx, 0, CHIP_W, 44), '', C_TX, size=20, visible=vis)",
              "btn(strip, 'ButtonSceneChip%d' % (i + 1), (cx, 0, CHIP_W, 60), '', C_TX, size=20, visible=vis)")
t = t.replace("""        tv(strip, 'TextChip%d' % (i + 1), (cx, 0, CHIP_W, 44),""",
              """        tv(strip, 'TextChip%d' % (i + 1), (cx, 0, CHIP_W, 60),""")
open(gp, 'w', encoding='utf-8').write(t)
print('gen_pages.py: chip 100x60 / step 108 / 滑动窗高 60（y=388）')
