# -*- coding: utf-8 -*-
"""相册上传页「接收模式」帧动画：8 帧旋转弧（48x48，主强调绿 #7BE0A3）。
   al_anim_0.png .. al_anim_7.png（每帧 270 度弧，起点差 45 度 → 转起来像接收/加载）
画法：SS=4 超采样 + BOX 面积平均（弧线有正确覆盖率，过 corner_audit 弧线过渡审计）。
用法：python ui/_gen/gen_album_anim.py
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
GN = (0x7B, 0xE0, 0xA3, 255)
GN_DIM = (0x7B, 0xE0, 0xA3, 90)
SS = 4
W = H = 48
TH = 4          # 弧线粗细（设备像素）


def frame(idx, total=8):
    im = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = TH // 2 + 2
    box = [pad * SS, pad * SS, (W - pad) * SS - 1, (H - pad) * SS - 1]
    start = idx * (360.0 / total)
    # 底圈（弱） + 主弧（亮，270 度）
    d.arc(box, start=0, end=360, fill=GN_DIM, width=TH * SS)
    d.arc(box, start=start, end=start + 270, fill=GN, width=TH * SS)
    return im.resize((W, H), Image.BOX)


def main():
    os.makedirs(IMGS, exist_ok=True)
    for i in range(8):
        im = frame(i)
        p = os.path.join(IMGS, 'al_anim_%d.png' % i)
        im.save(p)
    print('al_anim_0..7.png  48x48x8  %d B each'
          % os.path.getsize(os.path.join(IMGS, 'al_anim_0.png')))


if __name__ == '__main__':
    main()
