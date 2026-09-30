# -*- coding: utf-8 -*-
"""修「按键配置」行的 UI 布局（钟工 2026-09-29 17:23：设置界面下按键配置的 UI 布局不对）

根因：`add_keyset_page.py` 里克隆 7 个控件时把 top 一律写成行顶（396），
      没带行内相对偏移 → 图标/标签/值/箭头全叠在行顶部。
正确偏移照「屏保显示」行（它是对的）：Bg +0 / Label +6 / IconBg +8 / Icon +15 / Chevron +15 / Value +27
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sp = os.path.join(ROOT, 'ui', 'settings.json')
d = json.load(io.open(sp, encoding='utf-8'))
win = d['scrollwindow__1']['window__1']

BASE = 396
OFF = {
    'ButtonRowKeySetBg': 0,
    'ButtonRowKeySet': 0,
    'ButtonRowKeySetLabel': 6,
    'ButtonRowKeySetIconBg': 8,
    'ButtonRowKeySetIcon': 15,
    'ButtonRowKeySetChevron': 15,
    'ButtonRowKeySetValue': 27,
}
fixed = []
for k, v in win.items():
    if isinstance(v, dict) and v.get('caption') in OFF:
        cap = v['caption']
        p = dict(v['position'])
        p['top'] = BASE + OFF[cap]
        v['position'] = p
        fixed.append('%s -> top %d' % (cap, p['top']))
json.dump(d, io.open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
for f in sorted(fixed):
    print(' ·', f)
print('共 %d 个控件已归位' % len(fixed))

# 修完的对照检查（应与「屏保显示」行同一节奏）
win = json.load(io.open(sp, encoding='utf-8'))['scrollwindow__1']['window__1']
for basecap, base in (('ButtonRowKeySet', 396), ('ButtonRowSsSet', 452)):
    offs = sorted((v['position']['top'] - base, v['caption']) for v in win.values()
                  if isinstance(v, dict) and str(v.get('caption', '')).startswith(basecap))
    print('%s 行内偏移: %s' % (basecap, offs))
