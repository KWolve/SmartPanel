# -*- coding: utf-8 -*-
"""渲染 ui/main.preview.html 的各 window 页面 → proto_render/*.png（Edge headless）。"""
import os
import re
import subprocess
import sys

PRJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HTML = os.environ.get('SP_HTML') or os.path.join(PRJ, 'ui', 'main.preview.html')
OUT = os.path.join(PRJ, 'proto_render')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

t = open(HTML, encoding='utf-8').read()
print('preview html size', len(t))
ids = re.findall(r'id="([^"]+)"', t)
win_ids = [i for i in ids if 'window' in i.lower() or 'win' in i.lower()]
print('win-ish ids:', win_ids[:30])
print('has location.hash:', 'location.hash' in t)
print('has data-page switch:', t.count('showWnd'), t.count('page-btn'), t.count('switch'))

os.makedirs(OUT, exist_ok=True)
url = 'file:///' + HTML.replace('\\', '/').replace(' ', '%20')
# 尝试 #window__N 直达；若无效，退化为整页截图
targets = sys.argv[1:] or ['window__1', 'window__2', 'window__3']
for tgt in targets:
    png = os.path.join(OUT, tgt.replace('#', '') + '.png')
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars',
           '--window-size=520,560', '--screenshot=' + png, url + '#' + tgt]
    r = subprocess.run(cmd, capture_output=True)
    print(tgt, 'rc', r.returncode, os.path.getsize(png) if os.path.exists(png) else 'NOFILE', '->', png)
