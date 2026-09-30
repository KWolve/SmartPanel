# -*- coding: utf-8 -*-
"""修 keyset 页两处位置异常（钟工 2026-09-29 16:41：显示胶囊 + 底部提示栏位置不对）

根因（真机像素取证 device_480x480_20260929_153056.png）：
  · 行条 y = 84 / 136 / 188（高 46）；我克隆 ssset 时**胶囊自己写了 y+5** →
    实测绿胶囊 y = 89..132 / 141..184 / 193..236 = **比行条低、下沿还漏出 3px**
  · 对照真机 ssset（屏保显示）：条 top=80、胶囊 top=81 → 胶囊在条内居中（条+1）
  · 提示栏我放在 290/316/342（距最后一行 56px）；ssset 的约定是"行下 ~26px" →
    应放 260/286/312，整页才和前几个子页同一节奏
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
kp = os.path.join(ROOT, 'ui', 'keyset.json')
d = json.load(io.open(kp, encoding='utf-8'))

ROW_Y, ROW_H, ROW_GAP = 84, 46, 52
CHIP_X, CHIP_W, CHIP_H = 378, 68, 44
HINT_Y = ROW_Y + 3 * ROW_GAP - 6 + 26            # 最后一行底 280 → 提示从 306? 见下

changed = []
for i in range(3):
    y = ROW_Y + i * ROW_GAP
    for cap, ny, nh in (('ImageKsChip%d' % (i + 1), y + 1, CHIP_H),
                        ('TextKsRowValue%d' % (i + 1), y + 1, CHIP_H)):
        for k, v in d.items():
            if isinstance(v, dict) and v.get('caption') == cap:
                v['position'] = {'left': CHIP_X, 'top': ny, 'width': CHIP_W, 'height': nh}
                changed.append('%s -> top %d (条 top %d +1，居中)' % (cap, ny, y))

# 提示栏：按 ssset 的"行下 ~26px"节奏（最后一行底 = 84+2*52+46-1 = 233）
base = ROW_Y + 2 * ROW_GAP + ROW_H - 1 + 26      # 259
for idx, cap in enumerate(('TextKsHint1', 'TextKsHint2', 'TextKsHint3')):
    ny = base + idx * 26
    for k, v in d.items():
        if isinstance(v, dict) and v.get('caption') == cap:
            v['position'] = {'left': 20, 'top': ny, 'width': 440, 'height': 22}
            changed.append('%s -> top %d' % (cap, ny))

json.dump(d, io.open(kp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
for c in changed:
    print(' ·', c)
print('已改 %d 处' % len(changed))
