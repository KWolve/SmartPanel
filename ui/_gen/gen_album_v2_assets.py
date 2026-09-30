# -*- coding: utf-8 -*-
"""相册页 v2 需要的新素材（SS=4 + BOX，过 AA/弧线审计）：
  qr_card_160.png        160x160 白色圆角卡（二维码底）
  btn_regular440x48.png  440x48  常规按钮（#31313A 底 + 1px #3E3E48 描边，圆角 14）
  cnt56x24.png           56x24   绿底数量徽标（图片）
  cnt68x24.png           68x24   绿底数量徽标（视频）
用法：python ui/_gen/gen_album_v2_assets.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
IC = (0x31, 0x31, 0x3A, 255)
IC_BD = (0x3E, 0x3E, 0x48, 255)
GN = (0x7B, 0xE0, 0xA3, 255)
GN_BD = (0x62, 0xC0, 0x88, 255)
SS = 4


def rounded(w, h, r, fill, border=None, bw=1):
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if border is not None:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r * SS, fill=border)
        i = bw * SS
        d.rounded_rectangle([i, i, w * SS - 1 - i, h * SS - 1 - i],
                            radius=max(0, (r - bw) * SS), fill=fill)
    else:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r * SS, fill=fill)
    return im.resize((w, h), Image.BOX)


def main():
    os.makedirs(IMGS, exist_ok=True)
    items = [
        ('qr_card_160.png', rounded(160, 160, 16, (0xFF, 0xFF, 0xFF, 255))),
        ('btn_regular440x48.png', rounded(440, 48, 14, IC, IC_BD, 1)),
        ('cnt56x24.png', rounded(56, 24, 12, GN, GN_BD, 1)),
        ('cnt68x24.png', rounded(68, 24, 12, GN, GN_BD, 1)),
    ]
    for name, im in items:
        p = os.path.join(IMGS, name)
        im.save(p)
        print('%-24s %sx%s %5d B' % (name, im.size[0], im.size[1], os.path.getsize(p)))


if __name__ == '__main__':
    main()
