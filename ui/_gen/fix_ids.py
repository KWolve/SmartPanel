# -*- coding: utf-8 -*-
"""给 id=0 的控件分配全局唯一 id（生成器会丢弃 id=0 的控件 → 头文件里查不到指针）。

用法：python ui/_gen/fix_ids.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')


def main():
    maxid = {}
    pages = sorted(glob.glob(os.path.join(UI, '*.json')))
    docs = {}
    for p in pages:
        doc = json.load(open(p, encoding='utf-8'))
        docs[p] = doc
        for k, v in doc.items():
            if isinstance(v, dict) and '__' in k and v.get('id', 0) != 0:
                t = k.split('__')[0]
                maxid[t] = max(maxid.get(t, 0), v['id'])

    changed = []
    for p, doc in docs.items():
        dirty = False
        for k, v in doc.items():
            if not isinstance(v, dict) or '__' not in k:
                continue
            if v.get('id', 0) == 0:
                t = k.split('__')[0]
                maxid[t] = maxid.get(t, 0) + 1
                v['id'] = maxid[t]
                dirty = True
                changed.append('%s:%s=%d' % (os.path.basename(p), v.get('caption'), v['id']))
        if dirty:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
    print('assigned: %s' % (changed if changed else 'nothing (all ids set)'))


if __name__ == '__main__':
    main()
