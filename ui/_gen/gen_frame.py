# -*- coding: utf-8 -*-
"""屏体装饰外框 frame.png（原型 .dev 的 6px #2A2A32 / 圆角 30 边框）。
做法：SS≥4 超采样画「外圆角矩形 − 内圆角矩形」的环，再 BOX 面积平均降采样（禁 LANCZOS）。
"""
import os
from PIL import Image, ImageDraw

W = H = 480
BORDER = 6
R_OUT = 30
SS = 4
COLOR = (0x2A, 0x2A, 0x32, 255)


def ring(size, border, r_out, color):
    s = size * SS
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r_out * SS, fill=color)
    inset = border * SS
    d.rounded_rectangle([inset, inset, s - 1 - inset, s - 1 - inset],
                        radius=max(0, (r_out - border) * SS), fill=(0, 0, 0, 0))
    return im.resize((size, size), Image.BOX)


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       'resources', 'images', 'frame.png')
    im = ring(W, BORDER, R_OUT, COLOR)
    im.save(out)
    a = im.split()[3]
    print('frame.png', im.size, im.mode, os.path.getsize(out), 'B')
    print('alpha: edge(x=2,y=240)=%d  ring(x=3,y=240)=%d  center=%d  corner(3,3)=%d'
          % (a.getpixel((2, 240)), a.getpixel((3, 240)), a.getpixel((240, 240)), a.getpixel((3, 3))))
    print('rgb(3,240)=', im.getpixel((3, 240)))


if __name__ == '__main__':
    main()
