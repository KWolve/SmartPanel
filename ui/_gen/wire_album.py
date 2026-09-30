# -*- coding: utf-8 -*-
"""相册上传行接线：settingsLogic 的相册行 -> openActivity("albumActivity")。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'src', 'logic', 'settingsLogic.cc')
t = open(p, encoding='utf-8').read()

hits = re.findall(r'static bool on\w*Album\w*\(ZKButton \*pButton\)[^\n]*', t)
print('album 回调命中:', [h[:90] for h in hits])
assert hits, '未找到相册行回调'

for h in hits:
    name = re.match(r'static bool (\w+)\(', h).group(1)
    old = h
    new = (''.join([
        'static bool %s(ZKButton *pButton) {\n' % name,
        '    (void)pButton;\n',
        '    noteActivity();\n',
        '    EASYUICONTEXT->openActivity("albumActivity");\n',
        '    return true;\n',
        '}']))
    t = t.replace(old, new, 1)
    print('接线:', name, '-> albumActivity')

open(p, 'w', encoding='utf-8').write(t)
