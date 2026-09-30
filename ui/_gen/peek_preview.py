# -*- coding: utf-8 -*-
import re, os
P = r'C:\Users\zkswe\.openclaw\workspace\projects\SmartPanel_HA\ui\main.preview.html'
t = open(P, encoding='utf-8').read()
for m in re.finditer(r'WinSet', t):
    i = m.start()
    print('...', t[max(0, i - 260):i + 120].replace('\n', ' | ')[-380:])
    print('---')
    break
# 找切换逻辑
for kw in ('function ', 'addEventListener', 'checked', 'querySelector'):
    idxs = [m.start() for m in re.finditer(re.escape(kw), t)][:3]
    for i in idxs:
        print(kw, '>>', t[i:i + 220].replace('\n', ' '))
