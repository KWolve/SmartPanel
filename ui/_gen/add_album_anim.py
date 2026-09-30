# -*- coding: utf-8 -*-
"""相册上传页：加「接收模式」帧动画卡（钟工 2026-09-25 11:57 第 2 条）。
  - 新增 ImageAlAnimCard(452x50 底条 y330) + ImageAlAnim(48x48 帧动画) + TextAlAnimLabel(状态文字)
  - 「重新广播」按钮移到居中 y396（原 y350），避免与动画卡重叠
用法：python ui/_gen/add_album_anim.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'album.json')


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


def by_caption(doc, cap):
    for k, v in doc.items():
        if isinstance(v, dict) and v.get('caption') == cap:
            return k, v
    return None, None


def tv(cap, l, t, w, h, size, color, align, text='', pic=None):
    d = {'id': 0, 'caption': cap, 'position': {'left': l, 'top': t, 'width': w, 'height': h},
         'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                          'color3': -1, 'color4': -1},
         'fontSize': size, 'touchable': False, 'bold': False, 'italic': False, 'text': text,
         'visible': True, 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
         'rollStep': 5, 'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                                       'color4': -1}}
    if pic:
        d['backgroundPic'] = pic
    return d


def main():
    doc = json.load(open(P, encoding='utf-8'))
    caps = {v.get('caption') for v in doc.values() if isinstance(v, dict)}
    nxt = max([int(k.split('__')[1]) for k in doc if k.startswith('textview__')] or [0])
    maxid = global_max_id('textview__')
    added = []

    # 1) 按钮整组下移居中
    for cap in ('ImageAlChipBg', 'ButtonAlReboot', 'TextAlChip'):
        k, v = by_caption(doc, cap)
        if k and v['position']['top'] == 350:
            v['position'] = {'left': 164, 'top': 396, 'width': 152, 'height': 44}

    # 2) 帧动卡 + 动画 + 状态文字
    news = [
        ('ImageAlAnimCard', 14, 330, 452, 50, 16, 0xECECF0, 5, '', 'images/srow452x50.png'),
        ('ImageAlAnim', 32, 331, 48, 48, 16, 0xECECF0, 5, '', 'images/al_anim_0.png'),
        ('TextAlAnimLabel', 96, 343, 350, 24, 18, 0x9A9AA2, 1, '等待手机连接...', None),
    ]
    for cap, l, t, w, h, size, color, align, text, pic in news:
        if cap in caps:
            continue
        nxt += 1
        maxid += 1
        o = tv(cap, l, t, w, h, size, color, align, text, pic)
        o['id'] = maxid
        doc['textview__%d' % nxt] = o
        added.append(cap)

    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('album.json: +%d controls %s' % (len(added), added))


if __name__ == '__main__':
    main()
