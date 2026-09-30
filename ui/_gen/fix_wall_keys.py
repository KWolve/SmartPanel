# -*- coding: utf-8 -*-
"""修 gen_wall 留下的非标准键：settings.json 里 textview__wall_* / button__wall
-> 按现有最大编号续号，改名成 textview__N / button__N（生成器才认，指针才生成）。"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
p = os.path.join(UI, 'settings.json')
d = json.load(io.open(p, encoding='utf-8'))

# 找宿主容器（含 wall 键的那个 dict）与当前最大编号
host = None
mx = {'textview__': 0, 'button__': 0}


def scan(o):
    global host
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, dict):
                for pre in mx:
                    if k.startswith(pre) and k[len(pre):].isdigit():
                        mx[pre] = max(mx[pre], int(k[len(pre):]))
                if any(str(k).startswith('textview__wall') or str(k).startswith('button__wall')
                       for k in o.keys()):
                    host = o
                scan(v)
            elif isinstance(v, list):
                for x in v:
                    scan(x)
    elif isinstance(o, list):
        for x in o:
            scan(x)


scan(d)
if host is None:
    print('! 找不到 wall 键宿主，可能已改好')
else:
    new = {}
    order = []
    for k in list(host.keys()):
        v = host[k]
        if isinstance(k, str) and k.startswith('textview__wall'):
            mx['textview__'] += 1
            nk = 'textview__%d' % mx['textview__']
        elif isinstance(k, str) and k.startswith('button__wall'):
            mx['button__'] += 1
            nk = 'button__%d' % mx['button__']
        else:
            nk = k
        new[nk] = v
        order.append((k, nk))
    host.clear()
    host.update(new)
    for a, b in order:
        if a != b:
            print('  %-22s -> %s' % (a, b))
    json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('settings.json 键名已规范化')
