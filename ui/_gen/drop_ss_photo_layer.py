# -*- coding: utf-8 -*-
"""从 main.json 移除已弃用的 ImageSsPhoto 控件（改为复用最底层 ImageSsBg 铺图，避免压住屏保浮层）。
用法：python ui/_gen/drop_ss_photo_layer.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'main.json')


def main():
    d = json.load(open(P, encoding='utf-8'))
    removed = []
    for k in list(d.keys()):
        v = d[k]
        if isinstance(v, dict) and v.get('caption') == 'ImageSsPhoto':
            del d[k]
            removed.append(k)
    if removed:
        json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('main.json: removed %s' % (removed if removed else 'nothing'))


if __name__ == '__main__':
    main()
