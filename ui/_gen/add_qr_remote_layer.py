# -*- coding: utf-8 -*-
"""给相册页加「远端小程序码图」层（钟工 2026-09-25 16:21：小程序已做好，面板显示其小程序码）：
  ImageAlQrRemote 128x128 @(176,146)，默认隐藏；运行时下载小程序码 PNG 到本地后铺在这层上，
  并隐藏本地生成的二维码控件（QrcodeAl）。
用法：python ui/_gen/add_qr_remote_layer.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'album.json')
CAP = 'ImageAlQrRemote'


def global_max_tv():
    m = 0
    for p in glob.glob(os.path.join(ROOT, 'ui', '*.json')):
        d = json.load(open(p, encoding='utf-8'))

        def walk(o):
            nonlocal m
            for k, v in o.items():
                if isinstance(v, dict) and k.startswith('textview__') and v.get('id', 0) > m:
                    m = v['id']
                if isinstance(v, dict):
                    walk(v)
        walk(d)
    return m


def main():
    d = json.load(open(P, encoding='utf-8'))
    if any(isinstance(v, dict) and v.get('caption') == CAP for v in d.values()):
        print('already present')
        return
    n = max([int(k.split('__')[1]) for k in d if k.startswith('textview__')] or [0]) + 1
    d['textview__%d' % n] = {
        'id': global_max_tv() + 1, 'caption': CAP,
        'position': {'left': 176, 'top': 146, 'width': 128, 'height': 128},
        'alignment': 5, 'colorTab': {'color0': 0xECECF0, 'color1': -1, 'color2': -1,
                                     'color3': -1, 'color4': -1},
        'fontSize': 16, 'touchable': False, 'bold': False, 'italic': False, 'text': '',
        'visible': False, 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
        'rollStep': 5,
        'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}
    json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('album.json: + %s as textview__%d' % (CAP, n))


if __name__ == '__main__':
    main()
