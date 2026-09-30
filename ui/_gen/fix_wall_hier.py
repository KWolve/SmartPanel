# -*- coding: utf-8 -*-
"""把新追加的 wall 行控件从 scrollwindow__1 直接子键，移到它内部的 window 子键里
（scrollwindow/pagewindow 只装 window），并适当加高该 window 让新行可滚动到。
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'ui', 'settings.json')
d = json.load(io.open(p, encoding='utf-8'))

WALL_KEYS = ('ImageRowWallBg', 'ButtonRowWall', 'TextRowWallLabel', 'TextRowWallValue',
             'TextRowWallChevron')


def find(o, key, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                out.append(v)
            find(v, key, out)
    elif isinstance(o, list):
        for x in o:
            find(x, key, out)


sc = []
find(d, 'scrollwindow__1', sc)
if not sc:
    print('! 找不到 scrollwindow__1')
else:
    sw = sc[0]
    # 找内部 window 子键
    wins = [k for k in sw.keys() if str(k).startswith('window__')]
    print('scrollwindow 内 window 子键:', wins)
    if not wins:
        print('! 没有 window 子键')
    else:
        host = sw[wins[0]]
        moved = []
        for k in list(sw.keys()):
            v = sw[k]
            if isinstance(v, dict) and v.get('caption') in WALL_KEYS:
                host[k] = v
                del sw[k]
                moved.append(v.get('caption'))
        # 加高 window 让新行（top 656..702）在内
        pos = host.get('position', {})
        if pos.get('height', 0) < 720:
            pos['height'] = 720
            host['position'] = pos
        print('已移入 window：%s' % ', '.join(moved))
        print('window 高度 -> %s' % host['position'].get('height'))
        json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
