# -*- coding: utf-8 -*-
"""把 homeLogic 里残留的 sDevOn 用法换成 RelayManager 调用（业务单例）。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'src', 'logic', 'homeLogic.cc')
t = open(p, encoding='utf-8').read()

# 行内 toggle：sDevOn[n] = !sDevOn[n];  ->  RelayManager::getInstance()->toggle(n+1);
t = re.sub(r'sDevOn\[(\d)\] = !sDevOn\[\1\];',
           lambda m: 'RelayManager::getInstance()->toggle(%d);' % (int(m.group(1)) + 1), t)

# 删掉残留的 LOGD（里面引用 sDevOn）
t = '\n'.join(l for l in t.split('\n') if 'sDevOn' not in l)

open(p, 'w', encoding='utf-8').write(t)
print('sDevOn 残留:', t.count('sDevOn'))
