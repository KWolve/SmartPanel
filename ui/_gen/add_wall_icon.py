# -*- coding: utf-8 -*-
"""给设置页「多屏拼接」行补左侧图标（钟工 2026-09-27 11:08）。

现状：该行是唯一没有图标的行（早期 gen_wall.py 追加时省了图标盒）。
做法（与其它 10 行同口径）：
  1) 加 ImageRowWallIconBg(34x34, left=28, top=662) + ImageRowWallIcon(20x20, left=35, top=669)
     —— 行 top=656 / 高 46，图标按垂直居中算；Icon 与同行箭头(669)同一基线；
  2) TextRowWallLabel left 34 -> 75（让位给图标，与其它 10 行 label 同基线）；
  3) 数值框(300..418)/箭头(424..450) 不动（已验过不重叠）；
  4) 新控件 id 全局唯一非 0（扫 ui/*.json 取全局最大后递增）。

图标资源：`images/ic_dualscreen_g20.png`（Tabler `dual-screen`，双屏语义；
本工程 icons 组件生成器 scripts/gen_icons.py，风格/配色与既有 ic_*_g20.png 同源；
`tools/qa/aa_audit.py` PASS：真缺陷 0 / WARN 0，mid=84）。
"""
import glob
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
P = os.path.join(UI, 'settings.json')
ICON = 'images/ic_dualscreen_g20.png'
ROW_TOP = 656          # 该行 top（行高 46）
NEW = [
    # caption,              模板 caption,          目标 (left, top)
    ('ImageRowWallIconBg', 'ButtonRowFlipIconBg', (28, ROW_TOP + 6)),    # 34x34 垂直居中
    ('ImageRowWallIcon',   'ButtonRowFlipIcon',   (35, ROW_TOP + 13)),   # 20x20，与箭头同基线
]


def global_max(ui_dir, kinds=('textview', 'button')):
    mx = {}
    for p in sorted(glob.glob(os.path.join(ui_dir, '*.json'))):
        try:
            doc = json.load(io.open(p, encoding='utf-8'))
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, dict):
                        if '__' in k:
                            kind = k.split('__')[0]
                            mx[kind] = max(mx.get(kind, 0), v.get('id', 0) or 0)
                        walk(v)
        walk(doc)
    return {k: mx.get(k, 0) for k in kinds}


d = json.load(io.open(P, encoding='utf-8'))
win = d['scrollwindow__1']['window__1']

tpl = {}
for k, v in win.items():
    if isinstance(v, dict):
        tpl[v.get('caption')] = json.loads(json.dumps(v))

maxsuf = {'textview': 0, 'button': 0}
for p in sorted(glob.glob(os.path.join(UI, '*.json'))):
    txt = io.open(p, encoding='utf-8').read()
    for kind, n in re.findall(r'"(textview|button)__(\d+)"', txt):
        maxsuf[kind] = max(maxsuf[kind], int(n))

ids = global_max(UI)
added = []
newkeys = {}
for cap, tcap, (l, t) in NEW:
    node = tpl[tcap]
    node['caption'] = cap
    ids['textview'] += 1
    node['id'] = ids['textview']
    node['position']['left'] = l
    node['position']['top'] = t
    node['touchable'] = False
    if cap == 'ImageRowWallIconBg':
        node['backgroundPic'] = 'images/sicon34x34.png'
    else:
        node['backgroundPic'] = ICON
    maxsuf['textview'] += 1
    key = 'textview__%d' % maxsuf['textview']
    newkeys[cap] = (key, node)
    added.append((cap, node['id'], node['position']))

# 手工让位：label left 34 -> 75
label_moved = None
for k, v in win.items():
    if isinstance(v, dict) and v.get('caption') == 'TextRowWallLabel':
        v['position']['left'] = 75
        label_moved = (k, v['id'], v['position'])

# 插到 ButtonRowWall 之后（与其它行 z 序一致：bg, button, iconBg, icon, label, value, chevron）
out = {}
for k, v in win.items():
    out[k] = v
    if isinstance(v, dict) and v.get('caption') == 'ButtonRowWall':
        out[newkeys['ImageRowWallIconBg'][0]] = newkeys['ImageRowWallIconBg'][1]
        out[newkeys['ImageRowWallIcon'][0]] = newkeys['ImageRowWallIcon'][1]
win.clear()
win.update(out)

json.dump(d, io.open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('新增控件:')
for cap, i, pos in added:
    print('  %-22s id=%-6d L=%-4d T=%-4d W=%-4d H=%d  pic=%s' % (
        cap, i, pos['left'], pos['top'], pos['width'], pos['height'],
        newkeys[cap][1]['backgroundPic']))
print('label 让位: %s id=%s left=%s' % (label_moved[0], label_moved[1], label_moved[2]['left']))
print('window 键数: %d' % len(win))
