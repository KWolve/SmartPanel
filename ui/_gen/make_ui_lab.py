# -*- coding: utf-8 -*-
"""把 SmartPanel_HA 的 UI 层**单独拉出来**成一个可独立迭代的设计工作区（钟工 2026-09-24 23:17）：
  projects/PanelUI_Lab/
    ui/*.json          ← 当前 7 页布局（改这里做新一版设计）
    resources/images/  ← 当前全部图片资源
    font/*.ttf         ← 字体
    render.py          ← json → HTML → PNG 批量出图（Edge headless），用于"确认效果"
    apply_to_project.py← 确认后把 ui/ + resources/ 回流到 SmartPanel_HA（带回滚备份）
    README.md
不动原工程，改坏也只是工作区的事。
"""
import os
import shutil
import subprocess
import sys

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..'))
SRC = os.path.join(WS, 'projects', 'SmartPanel_HA')
LAB = os.path.join(WS, 'projects', 'PanelUI_Lab')

os.makedirs(os.path.join(LAB, 'ui'), exist_ok=True)
os.makedirs(os.path.join(LAB, 'resources'), exist_ok=True)
os.makedirs(os.path.join(LAB, 'font'), exist_ok=True)

# ① 拷 ui json（不拷 ftu：ftu 是产物，改 json 后重新 pack 即可）
n = 0
for f in sorted(os.listdir(os.path.join(SRC, 'ui'))):
    if f.endswith('.json'):
        shutil.copy2(os.path.join(SRC, 'ui', f), os.path.join(LAB, 'ui', f))
        n += 1
print('copied ui json:', n)

# ② 拷图片资源 + 字体
cnt = 0
srcimg = os.path.join(SRC, 'resources', 'images')
dstimg = os.path.join(LAB, 'resources', 'images')
os.makedirs(dstimg, exist_ok=True)
for f in sorted(os.listdir(srcimg)):
    shutil.copy2(os.path.join(srcimg, f), os.path.join(dstimg, f))
    cnt += 1
print('copied images:', cnt)
for f in sorted(os.listdir(os.path.join(SRC, 'font'))):
    shutil.copy2(os.path.join(SRC, 'font', f), os.path.join(LAB, 'font', f))
print('copied fonts ok')

# ③ render.py：json -> HTML -> PNG（Edge headless）
render = r'''# -*- coding: utf-8 -*-
"""批量出预览图：ui/*.json -> ui/_preview/*.html -> proto_render/*.png（Edge headless，480x480）。
用法：python projects/PanelUI_Lab/render.py [页面名...]  (不传=全部)"""
import glob, os, subprocess, sys

LAB = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(LAB, '..', '..'))
J2H = os.path.join(WS, 'tools', 'ui_tools', 'json2html.py')
OUT = os.path.join(LAB, 'proto_render')
EDGE = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe']
edge = next((e for e in EDGE if os.path.exists(e)), None)
os.makedirs(OUT, exist_ok=True)

pages = sys.argv[1:] or [os.path.splitext(os.path.basename(p))[0]
                         for p in sorted(glob.glob(os.path.join(LAB, 'ui', '*.json')))]
for name in pages:
    j = os.path.join(LAB, 'ui', name + '.json')
    if not os.path.exists(j):
        print('skip (no json):', name); continue
    r = subprocess.run([sys.executable, J2H, j], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    html = None
    for cand in glob.glob(os.path.join(LAB, '**', name + '*.html'), recursive=True):
        html = cand
    if html is None:
        print('%-12s json2html 没出 html：%s' % (name, (r.stdout or r.stderr)[-200:])); continue
    png = os.path.join(OUT, name + '.png')
    if edge:
        subprocess.run([edge, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                        '--window-size=480,480', '--screenshot=' + png,
                        'file:///' + html.replace('\\', '/')], capture_output=True)
        print('%-12s -> %s (%d B)' % (name, png, os.path.getsize(png) if os.path.exists(png) else 0))
    else:
        print('%-12s html=%s（未找到 Edge/Chrome，跳过截图）' % (name, html))
'''
open(os.path.join(LAB, 'render.py'), 'w', encoding='utf-8').write(render)

# ④ apply_to_project.py：确认后回流
apply_ = r'''# -*- coding: utf-8 -*-
"""把 PanelUI_Lab 的 ui/*.json + resources/images/* 回流到 SmartPanel_HA（先备份到 projects/backup_ui_<时间>）。
用法：python projects/PanelUI_Lab/apply_to_project.py --yes"""
import argparse, datetime, os, shutil

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
LAB = os.path.join(WS, 'projects', 'PanelUI_Lab')
PRJ = os.path.join(WS, 'projects', 'SmartPanel_HA')

ap = argparse.ArgumentParser()
ap.add_argument('--yes', action='store_true', help='确实要写回（不加只打印计划）')
a = ap.parse_args()

pairs = [(os.path.join(LAB, 'ui'), os.path.join(PRJ, 'ui'), ('.json',)),
         (os.path.join(LAB, 'resources', 'images'), os.path.join(PRJ, 'resources', 'images'), ('.png',))]
if not a.yes:
    for s, d, ext in pairs:
        n = len([f for f in os.listdir(s) if f.endswith(ext)])
        print('计划: %s -> %s (%d 个 %s)' % (s, d, n, ext))
    print('加 --yes 才执行（会先自动备份原文件）')
    raise SystemExit(0)

stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak = os.path.join(WS, 'projects', 'backup_ui_' + stamp)
for s, d, ext in pairs:
    sub = os.path.join(bak, os.path.relpath(d, PRJ))
    os.makedirs(sub, exist_ok=True)
    for f in os.listdir(d):
        if f.endswith(ext):
            shutil.copy2(os.path.join(d, f), os.path.join(sub, f))
    for f in sorted(os.listdir(s)):
        if f.endswith(ext):
            shutil.copy2(os.path.join(s, f), os.path.join(d, f))
    print('回流完成:', d)
print('原文件备份 ->', bak)
print('接下来：cd projects/SmartPanel_HA/ui && fui pack ./ 然后 fun build -p Z20')
'''
open(os.path.join(LAB, 'apply_to_project.py'), 'w', encoding='utf-8').write(apply_)

readme = '''# PanelUI_Lab —— 面板 UI 设计工作区（独立于 SmartPanel_HA 工程）

> 目的：想改版 UI 时**在这里改**，效果确认后再回流到正式工程，避免把工程改坏。
> 来源：2026-09-24 从 `projects/SmartPanel_HA` 拉出的 UI 层（布局 json + 图片资源 + 字体）。

## 目录
| 路径 | 说明 |
|---|---|
| `ui/*.json` | 7 页布局：main(屏保) / home / settings / brightness / video / album / ssset |
| `resources/images/` | 全部图片资源（**自动生成图尺寸必须 == 控件盒**，否则 check_all 报错） |
| `font/` | HanSans-Medium（GB2312 全字库）+ HanSansLight |
| `render.py` | 批量出预览图：`python projects/PanelUI_Lab/render.py` → `proto_render/*.png`（480×480） |
| `apply_to_project.py` | 确认后回流到 SmartPanel_HA（自动备份原文件） |

## 工作流
1. 改 `ui/*.json`（和/或 `resources/images/`）
2. `python projects/PanelUI_Lab/render.py` → 看 `proto_render/*.png`（确认效果）
3. 确认 OK：`python projects/PanelUI_Lab/apply_to_project.py --yes` 回流
4. 回到正式工程：`cd projects/SmartPanel_HA/ui && fui pack ./`，然后 `fun build -p Z20`（可选 `flythings_pack_upgrade` 出 update.img）

## 约束（沿用正式工程口径）
- 深色 M3 配色：底 `#17171B` / 卡 `#26262E` / 强调绿 `#7BE0A3` / 主字 `#ECECF0` / 辅字 `#9A9AA2`
- 字体不含的特殊符号禁用（`℃`、`…`、`—`、`→`、`①` 等）；图标一律 PNG
- json 字段显式化、id 分段（textview 50001+ / button 20001+ / window 110001+ / scrollwindow 120001+ / seekbar 90000+ / edittext 51000+ / videoview 95000+）
- 960/480 屏：控件盒与图片尺寸必须一致（check_all 第 17 项）
- 改完跑 `python tools/ui_tools/check_all.py projects/SmartPanel_HA` 全 PASS 再推设备
'''
open(os.path.join(LAB, 'README.md'), 'w', encoding='utf-8').write(readme)

print('lab ->', LAB)
