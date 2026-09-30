# -*- coding: utf-8 -*-
"""修两条 FAIL：
1) mainLogic.cc 注释里的禁用字符 -> 纯文本
2) devname.json 的 edittext 补字段全集（对齐 SampleUI 基准：bold/hintTextColor/hintText/textType，alignment=4）
用法：python ui/_gen/fix_fails_09251751.py
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
SRC = os.path.join(ROOT, 'src')

# 1) mainLogic：禁用字符清理
p = os.path.join(SRC, 'logic', 'mainLogic.cc')
t = io.open(p, encoding='utf-8').read()
n = t.count('\u26a0')
for bad in ('\u26a0\ufe0f', '\u26a0'):
    t = t.replace(bad, '')
t = t.replace('// 绝不允许', '// 注意：绝不允许')
io.open(p, 'w', encoding='utf-8').write(t)
print('mainLogic: 去掉禁用字符 x%d' % n)

# 2) devname.json：edittext 字段全集
q = os.path.join(UI, 'devname.json')
d = json.load(io.open(q, encoding='utf-8'))


def walk(o):
    for k, v in o.items():
        if isinstance(v, dict):
            if k.startswith('edittext__'):
                v['alignment'] = 4                 # 左对齐 + 垂直居中（与基准一致）
                v['bold'] = False
                v['hintTextColor'] = 0x5F5F68
                v.setdefault('hintText', '输入设备名称')
                v['textType'] = 0
            walk(v)


walk(d)
json.dump(d, io.open(q, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('devname.json: edittext 字段补齐')

# 3) 同步生成脚本（下次重生成不丢字段）
g = os.path.join(UI, '_gen', 'gen_devname.py')
g = g.replace('_gen', '_gen') if False else os.path.join(ROOT, 'ui', '_gen', 'gen_devname.py')
s = io.open(g, encoding='utf-8').read()
if 'hintTextColor' not in s:
    s = s.replace(
        """             'password': False, 'maxLength': 24, 'inputType': 0}""",
        """             'password': False, 'maxLength': 24, 'inputType': 0,
             'bold': False, 'hintTextColor': 0x5F5F68, 'hintText': '输入设备名称',
             'textType': 0}""")
    s = s.replace("""             'alignment': AL_LT, 'fontSize': 20, 'text': text, 'touchable': True,""",
                  """             'alignment': 4, 'fontSize': 20, 'text': text, 'touchable': True,""")
    io.open(g, 'w', encoding='utf-8').write(s)
    print('gen_devname.py: 字段模板已同步')
