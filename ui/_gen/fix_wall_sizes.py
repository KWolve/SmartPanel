# -*- coding: utf-8 -*-
"""把新增控件的尺寸对齐到复用资源的实际尺寸（check_all #11 要求 PNG 尺寸 == 控件盒）：
 settings.json 新行：背景 440x50 -> 452x46（用 srow452x46.png）；箭头 20x20 -> 26x20（文本 '>' 最小尺寸）
 wall.json：状态卡 452x44 -> 452x46；保存/返回底 214x32 -> 216x48（用 af_btn216x48.png）
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')


def walk(o, fn):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if isinstance(v, dict):
                fn(k, v)
                walk(v, fn)
            elif isinstance(v, list):
                for x in v:
                    walk(x, fn)
    elif isinstance(o, list):
        for x in o:
            walk(x, fn)


# ── settings.json ──
p = os.path.join(UI, 'settings.json')
d = json.load(io.open(p, encoding='utf-8'))
cnt = {'bg': 0, 'chev': 0}


def fix_settings(k, v):
    cap = str(v.get('caption', ''))
    pos = v.get('position')
    if not pos:
        return
    if cap == 'ImageRowWallBg':
        pos['height'] = 46
        pos['width'] = 452
        cnt['bg'] += 1
    if cap == 'TextRowWallChevron':
        pos['width'] = 26
        pos['height'] = 20
        cnt['chev'] += 1


walk(d, fix_settings)
json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('settings.json: 背景行改 452x46 x%d；箭头改 26x20 x%d' % (cnt['bg'], cnt['chev']))

# ── wall.json ──
p2 = os.path.join(UI, 'wall.json')
d2 = json.load(io.open(p2, encoding='utf-8'))
cnt2 = {'st': 0, 'btn': 0}


def fix_wall(k, v):
    cap = str(v.get('caption', ''))
    pos = v.get('position')
    if not pos:
        return
    if cap == 'ImageWallStatusBg':
        pos['height'] = 46
        pos['top'] = 376
        cnt2['st'] += 1
    if cap in ('ImageWallSaveBg', 'ImageWallHintBg'):
        pos['width'] = 216
        pos['height'] = 48
        pos['top'] = 428
        pos['left'] = 14 if cap == 'ImageWallSaveBg' else 246
        cnt2['btn'] += 1
    if cap in ('ButtonWallSave', 'ButtonWallBack2'):
        pos['width'] = 216
        pos['height'] = 48
        pos['top'] = 428
        pos['left'] = 14 if cap == 'ButtonWallSave' else 246


walk(d2, fix_wall)
json.dump(d2, io.open(p2, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('wall.json: 状态卡改 452x46 x%d；底部按钮改 216x48 x%d' % (cnt2['st'], cnt2['btn']))
