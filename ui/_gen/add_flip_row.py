# -*- coding: utf-8 -*-
"""新增设置页「设备倒装」行（钟工 2026-09-27 10:43）。

做什么：
  1) 在 ui/settings.json 的「系统」组内、**版本信息 上方**插入一行「设备倒装」（值 开启/关闭）；
  2) 把「版本信息」行与其后的「多屏拼接」行整体下移 56（一行高 50 + 行距 6）；
  3) 内层 window 高度 720 -> 776（保证新增行能滚到）；
  4) id 全局唯一且非 0（扫 ui/*.json 取各类控件当前全局最大值后递增）。

几何与配色**直接深拷贝同目录既有行（屏幕亮度行）的节点**再改 id/caption/坐标，
口径天然一致：行 L=14 W=452 H=50、图标盒 34×34、label 18px、value 16px、箭头 26×20。
"""
import glob
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
P = os.path.join(UI, 'settings.json')

ROW_TOP = 592          # 插在「系统」组标题(568)与「版本信息」(原 592) 之间
SHIFT = 56             # 下移量（一行 50 + 间距 6）
ICON = 'images/ic_refresh_g20.png'      # 20×20 旋转语义图标（既有资源，尺寸==控件盒）

NEW = [
    # caption,            模板 caption,            相对(0,0)的左上角
    ('ButtonRowFlipBg',      'ButtonRowBrightBg',      (14, ROW_TOP)),
    ('ButtonRowFlip',        'ButtonRowBright',        (14, ROW_TOP)),
    ('ButtonRowFlipIconBg',  'ButtonRowBrightIconBg',  (28, ROW_TOP + 8)),
    ('ButtonRowFlipIcon',    'ButtonRowBrightIcon',    (35, ROW_TOP + 15)),
    ('ButtonRowFlipLabel',   'ButtonRowBrightLabel',   (75, ROW_TOP + 6)),
    ('ButtonRowFlipValue',   'ButtonRowBrightValue',   (75, ROW_TOP + 27)),
    ('ButtonRowFlipChevron', 'ButtonRowBrightChevron', (424, ROW_TOP + 15)),
]
SHIFT_PREFIX = ('ButtonRowVer', 'ImageRowWallBg', 'ButtonRowWall', 'TextRowWall')
NEW_CAPTIONS = tuple(n[0] for n in NEW)


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
        tpl[v.get('caption')] = json.loads(json.dumps(v))   # 深拷贝模板

# 键名后缀（textview__NN / button__NN）取全局最大，避免撞键
maxsuf = {'textview': 0, 'button': 0}
for p in sorted(glob.glob(os.path.join(UI, '*.json'))):
    try:
        txt = io.open(p, encoding='utf-8').read()
    except Exception:
        continue
    for kind, n in re.findall(r'"(textview|button)__(\d+)"', txt):
        maxsuf[kind] = max(maxsuf[kind], int(n))

ids = global_max(UI)
added = []
for cap, tcap, (l, t) in NEW:
    kind = 'button' if cap == 'ButtonRowFlip' else 'textview'
    if tcap not in tpl:
        raise SystemExit('模板缺失: %s' % tcap)
    node = tpl[tcap]
    node['caption'] = cap
    ids[kind] += 1
    node['id'] = ids[kind]
    node['position']['left'] = l
    node['position']['top'] = t
    if cap == 'ButtonRowFlipIcon':
        node['backgroundPic'] = ICON
    if cap == 'ButtonRowFlipLabel':
        node['text'] = '设备倒装'
    if cap == 'ButtonRowFlipValue':
        node['text'] = '关闭'
    if cap == 'ButtonRowFlipBg':
        node['backgroundPic'] = 'images/srow452x50.png'
    if cap == 'ButtonRowFlipIconBg':
        node['backgroundPic'] = 'images/sicon34x34.png'
    if cap == 'ButtonRowFlipChevron':
        node['backgroundPic'] = 'images/ic_chr_dim26.png'
    maxsuf[kind] += 1
    win['%s__%d' % (kind, maxsuf[kind])] = node
    added.append((cap, node['id'], node['position']))

# 版本信息 / 多屏拼接 整体下移
shifted = []
def walk_shift(node):
    if isinstance(node, dict):
        cap = node.get('caption')
        if isinstance(cap, str) and cap.startswith(SHIFT_PREFIX) and 'position' in node:
            node['position']['top'] += SHIFT
            shifted.append(cap)
        for v in node.values():
            walk_shift(v)
walk_shift(win)

win['position']['height'] = 720 + SHIFT

json.dump(d, io.open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('新增行:')
for cap, i, pos in added:
    print('  %-22s id=%-6d L=%-4d T=%-4d W=%-4d H=%d' % (cap, i, pos['left'], pos['top'],
                                                         pos['width'], pos['height']))
print('下移: %s' % ', '.join(shifted))
print('window height -> %d' % win['position']['height'])
