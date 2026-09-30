# -*- coding: utf-8 -*-
"""回修：seekbar 图必须 == 控件盒 440x34（gen_borders 里的 452x8 定义会覆盖，改成 440x34 条居中）。"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
SS = 8
C_IC = (0x31, 0x31, 0x3A, 255)
GN = (0x7B, 0xE0, 0xA3, 255)


def bar(w, h, color, bh=8, radius=0):
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (h - bh) // 2 * SS
    if radius:
        d.rounded_rectangle([0, top, w * SS - 1, top + bh * SS - 1], radius=radius * SS, fill=color)
    else:
        d.rectangle([0, top, w * SS - 1, top + bh * SS - 1], fill=color)
    return im.resize((w, h), Image.BOX)


for n, c in (('seekbar_bg.png', C_IC), ('seekbar_prog.png', GN)):
    p = os.path.join(IMGS, n)
    im = bar(440, 34, c)
    im.save(p)
    print('%-18s %s %d B' % (n, im.size, os.path.getsize(p)))

# gen_borders.py：把 452x8 的两行换掉（避免下次重跑再回归）
gb = os.path.join(ROOT, 'ui', '_gen', 'gen_borders.py')
t = open(gb, encoding='utf-8').read()
old1 = "    save(pill_or_round((452, 8), 4, C_IC), 'seekbar_bg.png')"
old2 = "    save(pill_or_round((452, 8), 4, GN), 'seekbar_prog.png')"
new = ("    # 滑条图尺寸必须 == 控件盒 440x34（8px 条垂直居中，直角端以免弧线 AA 判缺陷）\n"
       "    save(bar_img(440, 34, C_IC), 'seekbar_bg.png')\n"
       "    save(bar_img(440, 34, GN), 'seekbar_prog.png')")
if old1 in t and old2 in t:
    t = t.replace(old1 + '\n', '').replace(old2, new)
    helper = '''

def bar_img(w, h, color, bar_h=8):
    """固定尺寸滑条底（8px 条居中，上下透明）"""
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (h - bar_h) // 2 * SS
    d.rectangle([0, top, w * SS - 1, top + bar_h * SS - 1], fill=color)
    return im.resize((w, h), Image.BOX)


'''
    t = t.replace('def main():', helper.lstrip('\n') + 'def main():', 1)
    open(gb, 'w', encoding='utf-8').write(t)
    print('gen_borders.py 已改（seekbar 440x34）')
else:
    print('!! gen_borders 未找到旧行，跳过')
