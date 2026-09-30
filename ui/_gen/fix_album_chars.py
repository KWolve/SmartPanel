# -*- coding: utf-8 -*-
"""去掉相册页文本里的设备字库黑名单字符（… — 等），并扫描一遍自证干净。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BAN = set('…—–℃■●⌫‹－＋')
BAN |= {chr(c) for c in range(0x2190, 0x2200)}   # 箭头
BAN |= {chr(c) for c in range(0x2460, 0x2500)}   # 圈号
BAN |= {chr(c) for c in range(0x2000, 0x2010)}   # 通用标点（含 ‘ ’ “ ” 等窄空格区）

REPL = {'…': '...', '—': '-', '–': '-', '－': '-', '＋': '+', '‹': '<', '⌫': '<-'}

files = ['ui/_gen/gen_pages.py', 'src/logic/albumLogic.cc']
for rel in files:
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    n = 0
    for ch, rep in REPL.items():
        if ch in t:
            n += t.count(ch)
            t = t.replace(ch, rep)
    # 剩下的黑名单字符（非文本上下文，直接删）
    left = [c for c in t if c in BAN]
    for c in set(left):
        t = t.replace(c, '')
    # 只在 python 字符串里替换过；C/C++ 注释里若还有 -> 也一并清掉
    open(p, 'w', encoding='utf-8').write(t)
    print('%-32s 替换 %d 处' % (rel, n))

# 自证：扫描生成物 + 逻辑文件
for rel in ['ui/album.json', 'src/logic/albumLogic.cc']:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print('%-32s (还没生成)' % rel)
        continue
    t = open(p, encoding='utf-8').read()
    bad = sorted({c for c in t if c in BAN})
    print('%-32s 黑名单残留: %s' % (rel, bad if bad else '无'))
