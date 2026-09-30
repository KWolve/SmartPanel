# -*- coding: utf-8 -*-
"""
gen_wall_preview.py -- 生成 ui/wall.preview.html（钟工 2026-09-27）

为什么需要本脚本：
  共用工具 tools/ui_tools/json2html.py 的 `_render_control()` **不递归 scrollwindow 的子 window**
  （scrollwindow 走“未知控件兜底”分支），而 wall.json 的 6 行设置项全在
  ScrollWallRows(window__) -> WindowWallRows(嵌套 window) 里 —— 直接跑共用工具会出一张**没有行**的
  空稿（实测 11.5KB vs 之前的 23KB），客户拿到的预览会以为整页是空的。

做法（不改共用工具、只在本工程内扩展）：
  载入共用模块 -> 只在内存里把 `_render_control` 包一层：scrollwindow/pagewindow 递归其子控件
  （其余控件、样式、图片内联、页签逻辑全部沿用共用工具）-> 生成 wall.preview.html。
  口径变化只影响本工程这一张图，且与共用工具的输出格式完全一致。

用法（工作区根目录）：  python projects/SmartPanel_HA/ui/_gen/gen_wall_preview.py
"""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # <项目>/ui/_gen
UI_DIR = os.path.dirname(HERE)                              # <项目>/ui
PRJ = os.path.dirname(UI_DIR)                               # <项目>
TOOL = os.path.join(os.path.dirname(os.path.dirname(PRJ)),
                    'tools', 'ui_tools', 'json2html.py')     # 工作区 tools/ui_tools/json2html.py


def load_tool():
    if not os.path.isfile(TOOL):
        sys.exit('[X] 未找到共用工具: %s' % TOOL)
    spec = importlib.util.spec_from_file_location('json2html_shared', TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def patch_scrollwindow(mod):
    """scrollwindow / pagewindow：递归子控件（子内容是 window，再由原实现递归其成员）。

    子 window **不输出自身盒子**：共用实现把 window 当普通 .ctrl 盒子画（缺 backgroundColor 时
    退成 #888888 灰底，且尺寸常大于滚动视口）—— 实测会把 6 行设置项整片盖住（渲染成一块灰）。
    设备上 window 只是无底容器，所以这里“展平”：只把它的子控件按原坐标接到滚动区里。
    """
    orig = mod._render_control

    def wrapper(k, v, depth, base_dir, edit):
        """子 window：跳过盒子，只回它的子控件（含其自身偏移）。"""
        inner = []
        for k2, v2 in v.items():
            if isinstance(v2, dict) and '__' in k2:
                inner.append(patched(k2, v2, depth + 1, base_dir, edit))
        return ''.join(inner)

    def patched(key, ctrl, depth=0, base_dir='', edit=False):
        ctype = key.split('__')[0]
        if ctype in ('scrollwindow', 'pagewindow'):
            pos = ctrl.get('position', {})
            style = mod._pos_style(pos)
            if not ctrl.get('visible', True):
                style += 'display:none;'
            inner = []
            for k2, v2 in ctrl.items():
                if isinstance(v2, dict) and '__' in k2:
                    sub = k2.split('__')[0]
                    if sub in ('window', 'pagewindow', 'scrollwindow'):
                        inner.append(wrapper(k2, v2, depth + 1, base_dir, edit))
                    else:
                        inner.append(patched(k2, v2, depth + 1, base_dir, edit))
            return ('<div class="ctrl %s" data-caption="%s" %s style="%s">%s</div>'
                    % (ctype, mod._esc(ctrl.get('caption', '')),
                       mod._da(key, ctrl, ctype, edit), style, ''.join(inner)))
        return orig(key, ctrl, depth, base_dir, edit)

    mod._render_control = patched


def fix_transparent_button_bg(html_path, json_path):
    """把「透明热区按钮」的预览灰底去成 transparent（保留下层文字/图标）。

    共用工具 `_color(-1)` 会返回默认 #888888 —— 而本项目（及本平台口径）里 **-1 = 全透明**，
    于是 wall 页 6 个行热区按钮（ButtonWallRow1..6，bgColorTab.color0 = -1）被画成
    不透明灰块，正好盖住后面的标签/值 —— 预览里 6 行看起来是「空灰条」。
    只在**本工程这份预览**里按 json 真实色值修正（不动共用工具）。
    """
    data = json.load(open(json_path, encoding='utf-8'))
    caps = {}

    def walk(o):
        if isinstance(o, dict):
            bt = o.get('bgColorTab')
            if o.get('caption') and isinstance(bt, dict):
                caps[o['caption']] = bt.get('color0', None)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    html = open(html_path, encoding='utf-8').read()
    pat = re.compile(r'<div class="ctrl button[^>]*data-cap="([^"]+)"[^>]*>')
    fixed = [0]

    def repl(m):
        cap = m.group(1)
        v = caps.get(cap)
        v = -1 if v is None else v
        if v < 0 and 'background-color:#888888;' in m.group(0):
            fixed[0] += 1
            return m.group(0).replace('background-color:#888888;', 'background-color:transparent;')
        return m.group(0)

    html = pat.sub(repl, html)
    open(html_path, 'w', encoding='utf-8').write(html)
    return fixed[0]


def main():
    mod = load_tool()
    patch_scrollwindow(mod)
    # 单文件模式：只重生 wall.json 一张稿（不碰其它页面的 *.preview.html）
    json_path = os.path.join(UI_DIR, 'wall.json')
    res = mod.json2html(json_path)
    print('json2html ->', res.get('success'), res.get('files') or res.get('error'))
    out = os.path.join(UI_DIR, 'wall.preview.html')
    n = fix_transparent_button_bg(out, json_path)
    print('透明热区按钮去灰底: %d 个' % n)
    out = os.path.join(UI_DIR, 'wall.preview.html')
    if os.path.isfile(out):
        txt = open(out, encoding='utf-8').read()
        print('wall.preview.html %d bytes；含 6 行设置项=%s；含“播放内容”=%s'
              % (len(txt), 'TextWallRowValue6' in txt, '播放内容' in txt))
    else:
        sys.exit('[X] 未生成 %s' % out)


if __name__ == '__main__':
    main()
