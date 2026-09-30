# -*- coding: utf-8 -*-
"""控件 id 全局唯一分配器（供 make_<page>.py 复用）。

背景：gen_pages._newid 是「每页从基数 +1 重新数」，所以不同页会出现重复 id。
新增页要求「全局唯一且非 0」（生成器会丢弃 id=0 的控件），做法：
  1. 扫 ui/*.json 全部控件，得到每类控件的当前全局最大 id（可跳过将被覆盖的页）；
  2. 用该最大值做起点，替换 gen_pages._newid，逐类递增。

键名（textview__N 等）仍由 gen_pages._next 计数，各页内部连续、无注释键。
"""
import glob
import json
import os

GEN_PAGES_KINDS = ('textview', 'button', 'window', 'scrollwindow', 'pagewindow',
                   'seekbar', 'listview', 'edittext', 'videoview')


def global_max(ui_dir, skip=()):
    """扫 ui/*.json 返回 {kind: maxId}（跳过 skip 里的文件名）。"""
    mx = {}
    for p in sorted(glob.glob(os.path.join(ui_dir, '*.json'))):
        if os.path.basename(p) in skip:
            continue
        try:
            doc = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue

        def walk(node):
            for k, v in node.items():
                if isinstance(v, dict) and '__' in k:
                    kind = k.split('__')[0]
                    mx[kind] = max(mx.get(kind, 0), v.get('id', 0) or 0)
                    walk(v)

        walk(doc)
    return mx


def install(gen_pages, skip=()):
    """把 gen_pages._newid 换成全局唯一分配器；返回起点 dict（打印用）。"""
    start = global_max(gen_pages.UI, skip)
    state = dict(start)

    def _newid(kind):
        state[kind] = state.get(kind, 0) + 1
        return state[kind]

    gen_pages._newid = _newid
    print('id start (global max): %s' % {k: state.get(k, 0) for k in GEN_PAGES_KINDS
                                         if state.get(k)})
    return state
