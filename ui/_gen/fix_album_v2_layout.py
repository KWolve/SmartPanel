# -*- coding: utf-8 -*-
"""修正相册页 v2 的三处 check_all FAIL（最小尺寸 / 素材尺寸）：
   - 呼吸灯素材改成 16x16（dot_pulse16.png，与控件盒一致）
   - TextAlModeSub 宽 310 -> 370（文本需 >=361）
   - 图片/视频标签与徽标重排：ImgLabel 150 / ImgBadge 186 / VidLabel 256x104 / VidBadge 366
用法：python ui/_gen/fix_album_v2_layout.py
"""
import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
P = os.path.join(ROOT, 'ui', 'album.json')


def make_pulse():
    W = H = 16
    SS = 4
    im = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = (W * SS) // 2
    r = int(W * SS * 0.38)
    # 外圈淡 + 内核实（视觉上像一颗呼吸灯芯片）
    d.ellipse([c - r - SS, c - r - SS, c + r + SS, c + r + SS], fill=(0x7B, 0xE0, 0xA3, 90))
    d.ellipse([c - r, c - r, c + r, c + r], fill=(0x7B, 0xE0, 0xA3, 255))
    out = im.resize((W, H), Image.BOX)
    p = os.path.join(IMGS, 'dot_pulse16.png')
    out.save(p)
    print('dot_pulse16.png', out.size, os.path.getsize(p), 'B')


def main():
    make_pulse()
    d = json.load(open(P, encoding='utf-8'))
    def setpos(cap, **kw):
        for k, v in d.items():
            if isinstance(v, dict) and v.get('caption') == cap:
                v['position'].update(kw)
                return True
        return False

    setpos('ImageAlPulse', left=416, top=86, width=16, height=16)
    setpos('TextAlModeSub', left=76, top=100, width=370, height=22)
    setpos('TextAlImgLabel', left=30, top=348, width=150, height=22)
    setpos('ImageAlImgBadge', left=186, top=347, width=56, height=24)
    setpos('TextAlImgCount', left=186, top=347, width=56, height=24)
    setpos('TextAlVidLabel', left=256, top=348, width=104, height=22)
    setpos('ImageAlVidBadge', left=366, top=347, width=68, height=24)
    setpos('TextAlVidCount', left=366, top=347, width=68, height=24)

    for k, v in d.items():
        if isinstance(v, dict) and v.get('caption') == 'ImageAlPulse':
            v['backgroundPic'] = 'images/dot_pulse16.png'

    json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('album.json: layout fixed')


if __name__ == '__main__':
    main()
