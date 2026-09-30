# -*- coding: utf-8 -*-
"""屏保视频列表的**素材类型图标**（钟工 2026-09-25 11:55：做成视频/图片的图标，不用文字）。

  badge_video.png 40x22 灰底 #31313A + 播放三角（浅色 #ECECF0）—— 视频
  badge_image.png 40x22 绿底 #7BE0A3 + 照片图标（深色 #10141A：相框 + 太阳 + 山）—— 图片

画法：SS=4 超采样自绘（圆角 + 多边形/圆 → BOX 面积平均），保证斜边/弧线有正确覆盖率（过 AA 审计）。
用法：python ui/_gen/gen_badges.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')

SURF = (0x31, 0x31, 0x3A, 255)     # 灰底（视频）
SURF_BD = (0x3E, 0x3E, 0x48, 255)
GN = (0x7B, 0xE0, 0xA3, 255)       # 绿底（图片）
GN_BD = (0x62, 0xC0, 0x88, 255)
LIGHT = (0xEC, 0xEC, 0xF0, 255)    # 灰底上的图标色
DARK = (0x10, 0x14, 0x1A, 255)     # 绿底上的图标色
SS = 4
W, H, R = 40, 22, 6


def chip(fill, border):
    im = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W * SS - 1, H * SS - 1], radius=R * SS, fill=border)
    inset = 1 * SS
    d.rounded_rectangle([inset, inset, W * SS - 1 - inset, H * SS - 1 - inset],
                        radius=max(0, (R - 1) * SS), fill=fill)
    return im


def badge_video():
    """灰底 + 播放三角（右侧留白，视觉重心居中）。"""
    im = chip(SURF, SURF_BD)
    d = ImageDraw.Draw(im)
    cx, cy = W * SS // 2, H * SS // 2
    half_h, half_w = 5 * SS, 4 * SS
    d.polygon([(cx - half_w, cy - half_h), (cx - half_w, cy + half_h), (cx + half_w, cy)],
              fill=LIGHT)
    return im.resize((W, H), Image.BOX)


def badge_image():
    """绿底 + 照片图标：相框描边 + 太阳（小圆）+ 山（折线三角）。"""
    im = chip(GN, GN_BD)
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 11 * SS, 5 * SS, 29 * SS, 17 * SS    # 相框
    t = 1 * SS
    d.rectangle([x0, y0, x1, y1], outline=DARK, width=t)
    # 太阳
    d.ellipse([x0 + 2 * SS, y0 + 2 * SS, x0 + 5 * SS, y0 + 5 * SS], fill=DARK)
    # 山（两个三角，底边贴相框内底）
    d.polygon([(x0 + 2 * SS, y1 - t), (x0 + 7 * SS, y1 - 7 * SS), (x0 + 12 * SS, y1 - t)],
              fill=DARK)
    d.polygon([(x0 + 8 * SS, y1 - t), (x0 + 13 * SS, y1 - 5 * SS), (x1 - 2 * SS, y1 - t)],
              fill=DARK)
    return im.resize((W, H), Image.BOX)


def main():
    os.makedirs(IMGS, exist_ok=True)
    for name, fn in (('badge_video.png', badge_video), ('badge_image.png', badge_image)):
        im = fn()
        p = os.path.join(IMGS, name)
        im.save(p)
        print('%-18s %sx%s %5d B' % (name, im.size[0], im.size[1], os.path.getsize(p)))


if __name__ == '__main__':
    main()
