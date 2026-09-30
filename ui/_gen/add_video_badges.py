# -*- coding: utf-8 -*-
"""给 video.json（屏保视频子页）列表**每行加「编号 + 视/图 徽标」**（设计说明书 3.4.5，幂等）。

注意：行控件**嵌在 scrollwindow 的内嵌 window 里**（scrollwindow__1 > window__1），
      不能在顶层加（会画到滚动区外面）。本脚本：
       1) 清掉历史误加到顶层的 Idx/Badge 控件（如有）
       2) 在内嵌 window 内按行插入 TextVidRowIdx<i> / ImageVidRowBadge<i>（全局唯一 id）
       3) 名称控件右移让位（x 34 -> 62，宽 340 -> 292）
用法：python ui/_gen/add_video_badges.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'video.json')
ROWS = 12
BADGE_X, BADGE_Y, BADGE_W, BADGE_H = 362, 8, 40, 22
IDX_X, IDX_Y, IDX_W, IDX_H = 30, 9, 28, 20


def global_max_textview_id():
    m = 0
    for p in glob.glob(os.path.join(ROOT, 'ui', '*.json')):
        data = json.load(open(p, encoding='utf-8'))

        def walk(o):
            nonlocal m
            for k, v in o.items():
                if isinstance(v, dict) and k.startswith('textview__') and v.get('id', 0) > m:
                    m = v['id']
                if isinstance(v, dict):
                    walk(v)
        walk(data)
    return m


def find_inner(doc):
    """返回内嵌 window（承载行控件的那个）的引用 + 其 key。"""
    for k, v in doc.items():
        if k.startswith('scrollwindow__') and isinstance(v, dict):
            for kk, vv in v.items():
                if kk.startswith('window__') and isinstance(vv, dict):
                    return vv, kk
    raise SystemExit('inner window not found')


def find_caption(container, cap):
    for k, v in container.items():
        if isinstance(v, dict) and v.get('caption') == cap:
            return k, v
    return None, None


def tv_layer(cap, l, t, w, h, size, color, align, text='', pic=None, visible=False):
    d = {'id': 0, 'caption': cap, 'position': {'left': l, 'top': t, 'width': w, 'height': h},
         'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                          'color3': -1, 'color4': -1},
         'fontSize': size, 'touchable': False, 'bold': False, 'italic': False, 'text': text,
         'visible': visible, 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
         'rollStep': 5, 'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                                       'color4': -1}}
    if pic:
        d['backgroundPic'] = pic
    return d


def main():
    doc = json.load(open(P, encoding='utf-8'))
    inner, inner_key = find_inner(doc)

    # 1) 清理误加到顶层的 Idx/Badge
    stray = [k for k, v in doc.items() if isinstance(v, dict)
             and str(v.get('caption', '')).startswith(('TextVidRowIdx', 'ImageVidRowBadge'))]
    for k in stray:
        del doc[k]

    # 2) 名称让位
    for i in range(1, ROWS + 1):
        k, c = find_caption(inner, 'TextVidRowName%d' % i)
        if k is None:
            continue
        pos = c['position']
        if pos['left'] == 34 and pos['width'] == 340:
            pos['left'] = 62
            pos['width'] = 292

    # 3) 插入编号 + 徽标（每个控件紧随同行名之后，保持行内顺序：底图 -> 按钮 -> 编号 -> 名称 -> 徽标 -> 勾）
    nxt = max([int(k.split('__')[1]) for k in inner if k.startswith('textview__')] or [0])
    maxid = global_max_textview_id()
    added = 0
    for i in range(1, ROWS + 1):
        y = (i - 1) * 42
        name_key, _ = find_caption(inner, 'TextVidRowName%d' % i)
        items = list(inner.items())
        idx = [j for j, (k, _) in enumerate(items) if k == name_key]
        at = (idx[0] + 1) if idx else len(items)
        newpairs = []
        if find_caption(inner, 'TextVidRowIdx%d' % i)[0] is None:
            nxt += 1
            maxid += 1
            o = tv_layer('TextVidRowIdx%d' % i, IDX_X, y + IDX_Y, IDX_W, IDX_H, 16, 0x5F5F68, 1,
                         text='%02d' % i)
            o['id'] = maxid
            newpairs.append(('textview__%d' % nxt, o))
            added += 1
        if find_caption(inner, 'ImageVidRowBadge%d' % i)[0] is None:
            nxt += 1
            maxid += 1
            o = tv_layer('ImageVidRowBadge%d' % i, BADGE_X, y + BADGE_Y, BADGE_W, BADGE_H, 14,
                         0xECECF0, 5, text='视', pic='images/badge_video.png')
            o['id'] = maxid
            newpairs.append(('textview__%d' % nxt, o))
            added += 1
        for off, (k, v) in enumerate(newpairs):
            items.insert(at + off, (k, v))
        inner.clear()
        for k, v in items:
            inner[k] = v

    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('video.json: +%d controls (inner=%s), stray_removed=%d'
          % (added, inner_key, len(stray)))


if __name__ == '__main__':
    main()
