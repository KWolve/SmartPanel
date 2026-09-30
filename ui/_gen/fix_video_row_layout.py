# -*- coding: utf-8 -*-
"""修正 video.json 行内布局：编号盒宽 28 -> 36（最小尺寸校验 "01" 需 >= 35x20），
   名称左 62 -> 70、宽 292 -> 284，避免与编号重叠。幂等。
用法：python ui/_gen/fix_video_row_layout.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'video.json')
ROWS = 12


def inner_window(doc):
    for k, v in doc.items():
        if k.startswith('scrollwindow__') and isinstance(v, dict):
            for kk, vv in v.items():
                if kk.startswith('window__') and isinstance(vv, dict):
                    return vv
    raise SystemExit('inner window not found')


def main():
    doc = json.load(open(P, encoding='utf-8'))
    inner = inner_window(doc)
    fixed = []
    for i in range(1, ROWS + 1):
        for k, v in inner.items():
            if not isinstance(v, dict):
                continue
            cap = v.get('caption', '')
            if cap == 'TextVidRowIdx%d' % i and v['position']['width'] != 36:
                v['position']['width'] = 36
                fixed.append(cap)
            if cap == 'TextVidRowName%d' % i:
                pos = v['position']
                if pos['left'] != 70 or pos['width'] != 284:
                    pos['left'] = 70
                    pos['width'] = 284
                    fixed.append(cap)
    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('video.json: fixed %d controls (%s)' % (len(fixed), fixed[:4]))


if __name__ == '__main__':
    main()
