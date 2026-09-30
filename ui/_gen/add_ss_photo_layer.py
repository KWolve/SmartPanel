# -*- coding: utf-8 -*-
"""给 main.json（屏保页）追加**照片层**（混播用：图片素材全屏显示，默认隐藏，幂等）。
  - ImageSsPhoto：480x480 全屏垫层，backgroundPic 运行时空（由代码按当前素材设置），id 全局唯一。
用法：python ui/_gen/add_ss_photo_layer.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'main.json')
CAP = 'ImageSsPhoto'


def global_max_textview_id():
    m = 0
    for p in glob.glob(os.path.join(ROOT, 'ui', '*.json')):
        d = json.load(open(p, encoding='utf-8'))
        for k, v in d.items():
            if isinstance(v, dict) and k.startswith('textview__') and v.get('id', 0) > m:
                m = v['id']
    return m


def main():
    doc = json.load(open(P, encoding='utf-8'))
    if any(isinstance(v, dict) and v.get('caption') == CAP for v in doc.values()):
        print('main.json: %s already present' % CAP)
        return
    n = max([int(k.split('__')[1]) for k in doc if k.startswith('textview__')] or [0]) + 1
    doc['textview__%d' % n] = {
        'id': global_max_textview_id() + 1, 'caption': CAP,
        'position': {'left': 0, 'top': 0, 'width': 480, 'height': 480},
        'alignment': 1, 'colorTab': {'color0': 0xECECF0, 'color1': -1, 'color2': -1,
                                     'color3': -1, 'color4': -1},
        'fontSize': 16, 'touchable': False, 'bold': False, 'italic': False,
        'text': '', 'visible': False, 'rollEnable': False, 'rollDirection': 1,
        'rollIntervalTime': 150, 'rollStep': 5, 'backgroundPic': '',
        'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}
    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('main.json: + %s as textview__%d (id=%d)' % (CAP, n, doc['textview__%d' % n]['id']))


if __name__ == '__main__':
    main()
