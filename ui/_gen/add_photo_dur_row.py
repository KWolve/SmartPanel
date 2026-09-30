# -*- coding: utf-8 -*-
"""屏保视频子页：新增「图片显示时长」chip 行（钟工 2026-09-25 11:57：图片时长可配，进屏保设置）。

布局改动（幂等）：
  - ScrollVid 高 300 -> 232（88..320）
  - 轮播间隔 label/chips 上移：label y398->326，chips y424->350
  - 新增 TextPhotoDurLabel(y400) + 5 个 chip（x=14+i*92, y=424, 68x44）：
    ChipPhotoDurBg<i> / ButtonPhotoDur<i> / TextPhotoDur<i>，文案 5s/10s/15s/30s/60s
用法：python ui/_gen/add_photo_dur_row.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'video.json')
LABELS = ['5s', '10s', '15s', '30s', '60s']
X0, STEP, CW, CH, CY = 14, 92, 68, 44, 424
LBL_Y = 400


def global_max_id(prefix):
    m = 0
    for p in glob.glob(os.path.join(ROOT, 'ui', '*.json')):
        data = json.load(open(p, encoding='utf-8'))

        def walk(o):
            nonlocal m
            for k, v in o.items():
                if isinstance(v, dict) and k.startswith(prefix) and v.get('id', 0) > m:
                    m = v['id']
                if isinstance(v, dict):
                    walk(v)
        walk(data)
    return m


def tv(cap, l, t, w, h, size, color, align, text='', pic=None, touch=False):
    d = {'id': 0, 'caption': cap, 'position': {'left': l, 'top': t, 'width': w, 'height': h},
         'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                          'color3': -1, 'color4': -1},
         'fontSize': size, 'touchable': touch, 'bold': False, 'italic': False, 'text': text,
         'visible': True, 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
         'rollStep': 5, 'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                                       'color4': -1}}
    if pic:
        d['backgroundPic'] = pic
    return d


def btn(cap, l, t, w, h):
    return {'id': 0, 'caption': cap, 'position': {'left': l, 'top': t, 'width': w, 'height': h},
            'alignment': 5, 'colorTab': {'color0': 0xECECF0, 'color1': 0xECECF0, 'color2': -1,
                                         'color3': -1, 'color4': -1},
            'fontSize': 18, 'text': '', 'touchable': True, 'visible': True,
            'picTab': {}, 'longClickTimeOut': -1, 'longClickIntervalTime': -1,
            'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}


def by_caption(container, cap):
    for k, v in container.items():
        if isinstance(v, dict) and v.get('caption') == cap:
            return k, v
    return None, None


def main():
    doc = json.load(open(P, encoding='utf-8'))
    caps = {v.get('caption') for v in doc.values() if isinstance(v, dict)}

    # 1) 滚动窗变矮
    k, sc = by_caption(doc, 'ScrollVid')
    if k and sc['position']['height'] != 232:
        sc['position']['height'] = 232

    # 2) 轮播间隔整行上移
    k, v = by_caption(doc, 'TextVidIntLabel')
    if k:
        v['position']['top'] = LBL_Y - 74
    for i in range(1, 7):
        for cap in ('ImageVidIntBg%d' % i, 'ButtonVidInt%d' % i, 'TextVidInt%d' % i):
            kk, vv = by_caption(doc, cap)
            if kk:
                vv['position']['top'] = CY - 74

    # 3) 新增图片时长行
    added = []
    nxt_tv = max([int(x.split('__')[1]) for x in doc if x.startswith('textview__')] or [0])
    nxt_btn = max([int(x.split('__')[1]) for x in doc if x.startswith('button__')] or [0])
    max_tv, max_btn = global_max_id('textview__'), global_max_id('button__')

    if 'TextPhotoDurLabel' not in caps:
        nxt_tv += 1
        max_tv += 1
        o = tv('TextPhotoDurLabel', 20, LBL_Y, 300, 24, 18, 0x9A9AA2, 1, text='图片显示时长')
        o['id'] = max_tv
        doc['textview__%d' % nxt_tv] = o
        added.append('TextPhotoDurLabel')
    for i, lb in enumerate(LABELS):
        x = X0 + i * STEP
        for cap, maker, cnt in (('ImagePhotoDurBg%d' % (i + 1), 'tv', 0),
                                ('ButtonPhotoDur%d' % (i + 1), 'btn', 1),
                                ('TextPhotoDur%d' % (i + 1), 'tv', 2)):
            if cap in caps:
                continue
            if maker == 'tv':
                nxt_tv += 1
                max_tv += 1
                o = tv(cap, x, CY, CW, CH, 18,
                       0xECECF0 if cnt == 2 else 0xECECF0, 5,
                       text=(lb if cnt == 2 else ''),
                       pic=('images/chip68x44.png' if cnt == 0 else None))
                o['id'] = max_tv
                doc['textview__%d' % nxt_tv] = o
            else:
                nxt_btn += 1
                max_btn += 1
                o = btn(cap, x, CY, CW, CH)
                o['id'] = max_btn
                doc['button__%d' % nxt_btn] = o
            added.append(cap)

    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('video.json: +%d controls %s' % (len(added), added[:6]))


if __name__ == '__main__':
    main()
