# -*- coding: utf-8 -*-
"""只生成 off.json（关屏设置页）—— 复用 gen_pages.py 的字段模板，避免整体重跑覆盖其它页。

用法：python ui/_gen/make_off.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pages  # noqa: E402

doc = gen_pages.build_off()
out = os.path.join(gen_pages.UI, 'off.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
print('written %s controls=%d' % (out, sum(1 for k in doc if '__' in k)))
