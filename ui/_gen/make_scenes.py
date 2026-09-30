# -*- coding: utf-8 -*-
"""只生成 scenes.json（情景模式子页）-- 复用 gen_pages.py 的字段模板，不重跑 main()。

id 分配同 make_mode.py：从「ui/*.json 当前全局最大 id + 1」起（含 mode.json，
所以两页的 id 连续且全局唯一）。

用法：python ui/_gen/make_scenes.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pages  # noqa: E402
import id_alloc    # noqa: E402

id_alloc.install(gen_pages, skip=('scenes.json',))
gen_pages._n.clear()

doc = gen_pages.build_scenes()
out = os.path.join(gen_pages.UI, 'scenes.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
print('written %s controls=%d' % (out, sum(1 for k in doc if '__' in k)))
