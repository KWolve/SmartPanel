# -*- coding: utf-8 -*-
"""开关卡片 9-patch 化（钟工 2026-09-29 19:51）

问题：主界面开关卡片底色图 card.png / card_hl.png 是 141x216 的定尺图；
      「按键配置」里关掉 1~2 个开关后，卡片会被拉成 216x216 / 460x216
      → 非等比横向拉伸：圆角被拉扁、1px 描边变粗，看着"拉伸感"。
做法：把两张卡片底图做成 .9.png（四周 1px marker 环 + 中间拉伸段），
      像素内容与原来逐像素一致（只加 marker），拉伸时圆角/描边保持原样。
      尺寸 141x216 → 成品 143x218（内容区仍 141x216，marker 环在外）。
接线：json / 代码里的 "images/card.png" → "images/card.9.png"，
      "images/card_hl.png" → "images/card_hl.9.png"。
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', '..', '..', 'tools', 'ui_tools'))
from PIL import Image, ImageDraw

import gen_res  # noqa: E402  (tools/ui_tools/gen_res.py)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
RADIUS = 16

PAIRS = [('card.png', 'card.9.png'), ('card_hl.png', 'card_hl.9.png')]


def make9(src_name, dst_name):
    """原图像素不动，仅四周加 1px marker 环（FT-009 规则，复用 gen_res.to_9patch）。"""
    img = Image.open(os.path.join(IMGS, src_name)).convert('RGBA')
    out = gen_res.to_9patch(img, RADIUS, IMGS, dst_name)
    # 校验 marker 环
    a = Image.open(os.path.join(IMGS, dst_name)).convert('RGBA')
    print('%-14s -> %-18s %s  (原 %s)' % (src_name, dst_name, a.size, img.size))
    return a.size


def patch_text_files():
    """把引用换成 .9.png（json + 代码字符串）。"""
    targets = []
    for sub in ('ui', 'src'):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, sub)):
            if os.sep + 'images' in dirpath or os.sep + '_gen' in dirpath:
                continue
            for f in files:
                if f.endswith(('.json', '.cc', '.cpp', '.h')):
                    targets.append(os.path.join(dirpath, f))
    n_json = n_code = 0
    for p in targets:
        t = open(p, encoding='utf-8').read()
        if 'card_hl.png' not in t and 'card.png' not in t:
            continue
        # 先换 hl，避免 "card.png" 命中 "card_hl.png" 的子串问题（两者不同，安全起见按序）
        new = t.replace('images/card_hl.png', 'images/card_hl.9.png')
        new = re.sub(r'images/card\.png', 'images/card.9.png', new)
        if new != t:
            open(p, 'w', encoding='utf-8').write(new)
            rel = os.path.relpath(p, ROOT)
            if p.endswith('.json'):
                n_json += 1
            else:
                n_code += 1
            print('   patched', rel,
                  'card.9.png x%d' % new.count('images/card.9.png'),
                  'card_hl.9.png x%d' % new.count('images/card_hl.9.png'))
    print('   合计 json=%d code=%d' % (n_json, n_code))


if __name__ == '__main__':
    for a, b in PAIRS:
        make9(a, b)
    print('-- 改引用 --')
    patch_text_files()
