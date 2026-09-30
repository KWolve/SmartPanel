# -*- coding: utf-8 -*-
"""修 check_all 报的 3 处：亮度页注释里的 ① ②、滑条图尺寸 != 控件盒、设置页亮度行图标尺寸。"""
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
GN = (0x7B, 0xE0, 0xA3, 255)
IC = (0x31, 0x31, 0x3A, 255)
SS = 4

# 1) 亮度页注释里的 ① ②（U+2460-24FF 在黑名单）
p = os.path.join(ROOT, 'src', 'logic', 'brightnessLogic.cc')
t = open(p, encoding='utf-8').read()
t = t.replace('①', '(1)').replace('②', '(2)')
open(p, 'w', encoding='utf-8').write(t)
print('brightnessLogic.cc: ①② -> (1)(2)')


# 2) 滑条图：尺寸必须 == 控件盒 440x34（8px 高条垂直居中，上下透明）
def bar(w, h, color, bar_h=8, radius=4):
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (h - bar_h) // 2 * SS
    d.rounded_rectangle([0, top, w * SS - 1, top + bar_h * SS - 1], radius=radius * SS, fill=color)
    return im.resize((w, h), Image.BOX)


for name, color in (('seekbar_bg.png', IC), ('seekbar_prog.png', GN)):
    im = bar(440, 34, color)
    q = os.path.join(IMGS, name)
    im.save(q)
    print('%-20s %s %d B' % (name, im.size, os.path.getsize(q)))

# 3) 设置页亮度行图标：改成 20x20 的 ic_bright_g20.png（由 gen_icons 出，这里只改引用）
gp = os.path.join(ROOT, 'ui', '_gen', 'gen_pages.py')
t = open(gp, encoding='utf-8').read()
t = t.replace("('row', 'ButtonRowBright', 'ic_sun_g22.png', '屏幕亮度', '工作 80% · 屏保 30%'),",
              "('row', 'ButtonRowBright', 'ic_bright_g20.png', '屏幕亮度', '工作 80% · 屏保 30%'),")
open(gp, 'w', encoding='utf-8').write(t)
print('gen_pages.py: 亮度行图标 -> ic_bright_g20.png')
