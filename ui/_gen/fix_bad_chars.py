# -*- coding: utf-8 -*-
"""把 src/logic/*.cc 里落在 check_all 特殊字符黑名单的符号换成 ASCII（注释里的箭头等）。"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# check_all._is_bad_char 的黑名单区间 + 常见黑名单字符
MAP = {'↔': '<->', '→': '->', '←': '<-', '↑': '^', '↓': 'v', '…': '...', '–': '-',
       '—': '--', '℃': '°C', '≤': '<=', '≥': '>=', '·': '.', '「': '"', '」': '"'}


def bad(c):
    o = ord(c)
    if c in ('…', '–', '—', '·', '℃', '「', '」'):
        return True
    return (0x2190 <= o <= 0x21FF or 0x2300 <= o <= 0x23FF or 0x25A0 <= o <= 0x25FF
            or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or 0x2100 <= o <= 0x214F
            or 0x2460 <= o <= 0x24FF or 0x1F000 <= o <= 0x1FAFF or o in (0xFE0F, 0x200D))


def main():
    out = []
    for p in glob.glob(os.path.join(ROOT, 'src', 'logic', '*.cc')):
        t = open(p, encoding='utf-8').read()
        hits = sorted(set(c for c in t if bad(c)))
        if not hits:
            out.append('%-46s clean' % os.path.basename(p))
            continue
        for c in hits:
            t = t.replace(c, MAP.get(c, '?'))
        open(p, 'w', encoding='utf-8').write(t)
        out.append('%-46s fixed: %s' % (os.path.basename(p),
                                        ' '.join('U+%04X' % ord(c) for c in hits)))
    log = os.path.join(ROOT, '..', '..', 'temp', 'chars_fix.txt')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('\n'.join(out).encode('ascii', 'replace').decode('ascii'))


if __name__ == '__main__':
    main()
