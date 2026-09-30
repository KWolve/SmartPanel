# -*- coding: utf-8 -*-
"""问题单 09251751 批处理 2（墨羽）：像素级布局修正
 - 3) 屏保显示页：显示/隐藏按键(68x44)大于所在行背景框(452x38) -> 行背景改为 46 高（上下各高 1px）
      注意：行背景要正好“上下各 1px”包住 chip（chip top=81 -> bg top=80, h=46），并换新资源 srow452x46.png
 - 5) 关屏设置页：启用关屏时段那行同理（chip top=77 -> bg top=76, h=46）
 - 4) 情景设置页：输入框(250x30)与添加按键(152x44)不匹配 -> 输入框高改为 46、top 336（比按键上下各高 1px）
 - 6) 对齐：album 的「图片 JPG/PNG」「视频 MP4」「混播说明」与 video 的「图片显示时长」原为水平居中(align=1)
      -> 改左对齐(align=0)，与其它页 label 口径一致
用法：python ui/_gen/patch_issues_layout.py
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
IMG = os.path.join(ROOT, 'resources', 'images')
WS = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, os.path.join(WS, 'tools', 'ui_tools'))
import gen_res  # noqa: E402

C_SF, C_IC = 0x26262E, 0x31313A


def rgb(c, a=255):
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF, a)


def load(fn):
    return json.load(io.open(os.path.join(UI, fn), encoding='utf-8'))


def save(fn, data):
    json.dump(data, io.open(os.path.join(UI, fn), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)


def walk(node, fn):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, dict):
                fn(k, v)
                walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk(v, fn)


# ── 倒角口径（2026-09-27 统一，与 fix_corners.py::rounded 同式）────────────
# SS=4 覆盖 + Image.BOX 面积平均，r=12，**无描边**（族内多数口径：srow452x50/38 等同款）
from PIL import Image as _PILImage, ImageDraw as _PILImageDraw
_SS = 4


def _rounded_cov(w, h, radius, fill):
    im = _PILImage.new('RGBA', (w * _SS, h * _SS), (0, 0, 0, 0))
    _PILImageDraw.Draw(im).rounded_rectangle(
        [0, 0, w * _SS - 1, h * _SS - 1], radius=radius * _SS, fill=fill)
    return im.resize((w, h), _PILImage.BOX)


def main():
    # 新行背景资源（452x46）
    gen_res.save(_rounded_cov(452, 46, 12, rgb(C_SF)), IMG, 'srow452x46.png')

    # ── 3) ssset 行背景 ──
    d = load('ssset.json')
    n = [0]

    def f3(k, v):
        cap = str(v.get('caption', ''))
        if cap.startswith('ImageSsSetRowBg'):
            v['position'] = {'left': 14, 'top': v['position']['top'] - 4,
                             'width': 452, 'height': 46}
            v['backgroundPic'] = 'images/srow452x46.png'
            n[0] += 1
    walk(d, f3)
    save('ssset.json', d)
    print('ssset: 行背景改 46 高 x%d' % n[0])

    # ── 5) off 行背景 ──
    d = load('off.json')
    n = [0]

    def f5(k, v):
        cap = str(v.get('caption', ''))
        if cap == 'ImageOffRowBg1':
            v['position'] = {'left': 14, 'top': 76, 'width': 452, 'height': 46}
            v['backgroundPic'] = 'images/srow452x46.png'
            n[0] += 1
    walk(d, f5)
    save('off.json', d)
    print('off: 行背景改 46 高 x%d' % n[0])

    # ── 4) scenes 输入框 ──
    d = load('scenes.json')
    n = [0]

    def f4(k, v):
        if str(v.get('caption', '')) == 'EditSceneAdd':
            v['position'] = {'left': 30, 'top': 336, 'width': 250, 'height': 46}
            n[0] += 1
    walk(d, f4)
    save('scenes.json', d)
    print('scenes: 输入框改 250x46 x%d' % n[0])

    # ── 6) 对齐修正 ──
    fix_align = {'album.json': ['TextAlImgLabel', 'TextAlVidLabel', 'TextAlMixHint'],
                 'video.json': ['TextPhotoDurLabel']}
    for fn, caps in fix_align.items():
        d = load(fn)
        n = [0]

        def f6(k, v, caps=caps):
            if str(v.get('caption', '')) in caps:
                v['alignment'] = 0        # 0 = 左对齐（与其它 label 一致）
                n[0] += 1
        walk(d, f6)
        save(fn, d)
        print('%s: 对齐改左对齐 x%d' % (fn, n[0]))


if __name__ == '__main__':
    main()
