# -*- coding: utf-8 -*-
"""给 ssset.json（屏保显示页）追加「编辑位置」按钮（幂等）：
  - ImageSsSetEditBg（btn_primary440x48.png 垫层） + ButtonSsSetEdit（绿底黑字）
用法：python ui/_gen/add_ssset_edit_btn.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'ssset.json')
L, T, W, H = 20, 412, 440, 48


def main():
    doc = json.load(open(P, encoding='utf-8'))
    caps = [v.get('caption') for v in doc.values() if isinstance(v, dict)]
    tv_i = max([int(k.split('__')[1]) for k in doc if k.startswith('textview__')] or [0])
    bt_i = max([int(k.split('__')[1]) for k in doc if k.startswith('button__')] or [0])
    added = []

    if 'ImageSsSetEditBg' not in caps:
        tv_i += 1
        doc['textview__%d' % tv_i] = {
            'id': 0, 'caption': 'ImageSsSetEditBg',
            'position': {'left': L, 'top': T, 'width': W, 'height': H},
            'alignment': 1, 'colorTab': {'color0': 0xECECF0, 'color1': -1, 'color2': -1,
                                         'color3': -1, 'color4': -1},
            'fontSize': 16, 'touchable': False, 'bold': False, 'italic': False,
            'text': '', 'visible': True, 'rollEnable': False, 'rollDirection': 1,
            'rollIntervalTime': 150, 'rollStep': 5, 'backgroundPic': 'images/btn_primary440x48.png',
            'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                           'color4': -1}}
        added.append('ImageSsSetEditBg')

    if 'ButtonSsSetEdit' not in caps:
        bt_i += 1
        doc['button__%d' % bt_i] = {
            'id': 0, 'caption': 'ButtonSsSetEdit',
            'position': {'left': L, 'top': T, 'width': W, 'height': H},
            'alignment': 5, 'colorTab': {'color0': 0x10141A, 'color1': 0x10141A, 'color2': -1,
                                         'color3': -1, 'color4': -1},
            'fontSize': 20, 'text': '编辑位置', 'touchable': True, 'visible': True,
            'picTab': {}, 'longClickTimeOut': -1, 'longClickIntervalTime': -1,
            'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                           'color4': -1}}
        added.append('ButtonSsSetEdit')

    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('ssset.json: added %s' % (added if added else 'nothing (already patched)'))


if __name__ == '__main__':
    main()
