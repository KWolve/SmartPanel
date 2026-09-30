# -*- coding: utf-8 -*-
"""把 C++ 注释/文本里的设备字库外字符换成 ASCII（铁律：屏幕字库裁剪，→ ①② · 等无字形）。
扫描 src/logic/*.cc + src/**/*.cpp，做幂等替换。

用法：python ui/_gen/fix_special_chars.py
"""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPL = {
    '→': '->', '←': '<-', '①': '(1)', '②': '(2)', '③': '(3)', '④': '(4)', '⑤': '(5)',
    '·': '-', '—': '-', '–': '-', '℃': 'C', '±': '+/-', '×': 'x', '≈': '~', '≥': '>=',
    '≤': '<=', '※': '*',
}


def main():
    files = glob.glob(os.path.join(ROOT, 'src', '**', '*.cc'), recursive=True)
    files += glob.glob(os.path.join(ROOT, 'src', '**', '*.cpp'), recursive=True)
    files += glob.glob(os.path.join(ROOT, 'src', '**', '*.h'), recursive=True)
    fixed = []
    for p in files:
        t = open(p, encoding='utf-8').read()
        o = t
        for k, v in REPL.items():
            if k in t:
                t = t.replace(k, v)
        if t != o:
            open(p, 'w', encoding='utf-8').write(t)
            fixed.append(os.path.relpath(p, ROOT))
    print('fixed: %s' % (fixed if fixed else 'nothing'))

    # 复查：还有没有非 ASCII、非中文常用标点的字符
    bad = {}
    for p in files:
        t = open(p, encoding='utf-8').read()
        for ch in t:
            if ord(ch) > 0x2000 and ch not in '，。（）「」：；、！？…《》"\'':
                bad.setdefault(os.path.relpath(p, ROOT), set()).add(ch)
    print('remaining suspicious: %s' % (bad if bad else 'none'))


if __name__ == '__main__':
    main()
