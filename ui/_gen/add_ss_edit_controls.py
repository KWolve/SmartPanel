# -*- coding: utf-8 -*-
"""给 main.json（屏保页）追加「位置编辑」用的控件（幂等）：
  - 5 个虚线框垫层 textview（ss_ed_{time,date,weather,th,bar}.png，默认隐藏）
  - 「完成」按钮（默认隐藏，编辑模式下显示）
用法：python ui/_gen/add_ss_edit_controls.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'ui', 'main.json')

FRAMES = [
    ('ImageEdTime',    'images/ss_ed_time.png',    (0, 86, 480, 140)),
    ('ImageEdDate',    'images/ss_ed_date.png',    (0, 236, 480, 28)),
    ('ImageEdWeather', 'images/ss_ed_weather.png', (188, 282, 168, 24)),
    ('ImageEdTh',      'images/ss_ed_th.png',      (0, 326, 480, 28)),
    ('ImageEdBar',     'images/ss_ed_bar.png',     (16, 396, 452, 40)),
]


def layer(cap, pic, l, t, w, h):
    return {'id': 0, 'caption': cap,
            'position': {'left': l, 'top': t, 'width': w, 'height': h},
            'alignment': 1, 'colorTab': {'color0': 0xECECF0, 'color1': -1, 'color2': -1,
                                         'color3': -1, 'color4': -1},
            'fontSize': 16, 'touchable': False, 'bold': False, 'italic': False,
            'text': '', 'visible': False, 'rollEnable': False, 'rollDirection': 1,
            'rollIntervalTime': 150, 'rollStep': 5, 'backgroundPic': pic,
            'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                           'color4': -1}}


def main():
    doc = json.load(open(P, encoding='utf-8'))
    tv_i = max([int(k.split('__')[1]) for k in doc if k.startswith('textview__')] or [0])
    bt_i = max([int(k.split('__')[1]) for k in doc if k.startswith('button__')] or [0])

    added = []
    for cap, pic, (l, t, w, h) in FRAMES:
        if any(v.get('caption') == cap for v in doc.values() if isinstance(v, dict)):
            continue
        tv_i += 1
        key = 'textview__%d' % tv_i
        doc[key] = layer(cap, pic, l, t, w, h)
        added.append(cap)

    # 「完成」按钮（编辑模式显示）
    if not any(v.get('caption') == 'ButtonSsEditDone' for v in doc.values() if isinstance(v, dict)):
        tv_i += 1
        doc['textview__%d' % tv_i] = layer('ImageSsEditDoneBg', 'images/btn_primary152x44.png',
                                           164, 428, 152, 44)
        bt_i += 1
        doc['button__%d' % bt_i] = {
            'id': 0, 'caption': 'ButtonSsEditDone',
            'position': {'left': 164, 'top': 428, 'width': 152, 'height': 44},
            'alignment': 5, 'colorTab': {'color0': 0x10141A, 'color1': 0x10141A, 'color2': -1,
                                         'color3': -1, 'color4': -1},
            'fontSize': 20, 'text': '完成', 'touchable': True, 'visible': False,
            'picTab': {}, 'longClickTimeOut': -1, 'longClickIntervalTime': -1,
            'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                           'color4': -1}}
        added.append('ButtonSsEditDone')

    # id 为 0 时由引擎分配；保持其它控件原样
    with open(P, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print('main.json: added %s' % (added if added else 'nothing (already patched)'))


if __name__ == '__main__':
    main()
