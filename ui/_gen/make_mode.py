# -*- coding: utf-8 -*-
"""只生成 mode.json（运行模式子页）-- 复用 gen_pages.py 的字段模板，不重跑 main()。

控件 id 口径：全局唯一且非 0（生成器丢弃 id=0）。
本脚本先扫 ui/*.json（跳过本页自身）算出各类控件当前全局最大 id，
再让 gen_pages._newid 从「全局最大 + 1」开始逐类递增分配。

用法：python ui/_gen/make_mode.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_pages  # noqa: E402
import id_alloc    # noqa: E402

id_alloc.install(gen_pages, skip=('mode.json',))
gen_pages._n.clear()

doc = gen_pages.build_mode()
out = os.path.join(gen_pages.UI, 'mode.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
print('written %s controls=%d' % (out, sum(1 for k in doc if '__' in k)))
