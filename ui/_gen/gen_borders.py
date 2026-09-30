# -*- coding: utf-8 -*-
"""设备卡 / 情景 chip 加可见外框（钟工 16:42：不是各页加边框，是「回家模式」chip 与「客厅灯」卡片模块要有外框）。

做法：PIL 自绘（SS=4 超采样 + Image.BOX 面积平均），外框色 = 令牌 #31313A（比卡底 #26262E 亮一档）。
- card.png      141×216 圆角 16（固定尺寸，不用 .9）
- chip.png       84×44  胶囊 22（情景 chip 固定宽 84，用固定尺寸图更稳）
- chip_on.png    84×44  选中态（绿底）
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')

SF = (0x26, 0x26, 0x2E, 255)     # 卡片/行/chip 表面
BD = (0x31, 0x31, 0x3A, 255)     # 外框（图标底令牌）
C_IC = (0x31, 0x31, 0x3A, 255)   # 图标底（滑条底轨）
GN = (0x7B, 0xE0, 0xA3, 255)     # 主强调绿
SS = 4


def pill_or_round(size, radius, fill, border=None, border_w=1):
    w, h = size
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if border is not None:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=border)
        inset = border_w * SS
        d.rounded_rectangle([inset, inset, w * SS - 1 - inset, h * SS - 1 - inset],
                            radius=max(0, (radius - border_w) * SS), fill=fill)
    else:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill)
    return im.resize((w, h), Image.BOX)


def save(im, name):
    p = os.path.join(IMGS, name)
    im.save(p)
    a = im.split()[3]
    print('%-14s %s %s %5d B  不透明像素 %d' % (name, im.size, im.mode, os.path.getsize(p),
                                              sum(1 for v in a.tobytes() if v == 255)))


def bar_img(w, h, color, bar_h=8):
    """固定尺寸滑条底（8px 条居中，上下透明）"""
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (h - bar_h) // 2 * SS
    d.rectangle([0, top, w * SS - 1, top + bar_h * SS - 1], fill=color)
    return im.resize((w, h), Image.BOX)


def main():
    save(pill_or_round((141, 216), 16, SF, BD), 'card.png')
    save(pill_or_round((100, 60), 30, SF, BD), 'chip.png')
    save(pill_or_round((100, 60), 30, GN), 'chip_on.png')
    # 高对比态（按下 / 选中共用）：绿底 + 深字（字色由代码 setTextColor 切）
    save(pill_or_round((100, 60), 30, GN), 'chip_hl.png')
    # 亮度滑条：底（深灰胶囊）+ 已选进度（绿胶囊）+ 拖柄（绿圆 + 轻投影）
    # 滑条图尺寸必须 == 控件盒 440x34（8px 条垂直居中，直角端以免弧线 AA 判缺陷）
    save(bar_img(440, 34, C_IC), 'seekbar_bg.png')
    save(bar_img(440, 34, GN), 'seekbar_prog.png')


if __name__ == '__main__':
    main()
