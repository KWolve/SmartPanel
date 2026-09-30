# -*- coding: utf-8 -*-
"""SmartPanel_HA UI 生成器 —— 输出 ui/main.json（多整屏 window 架构，480×480，Z20）。

设计基准：smarthome_panel_product_design_spec.md + index.html 原型（480×480 1:1）
字段全集：knowledge/uicontrols/json-field-mandatory.md（每类型必写键全部显式）
对齐位：bit0-1 水平(0左1中2右) / bit2-3 垂直(0顶1中2底) → 37=中中，38=右中，0=左顶

用法：python ui/_gen/gen_ui.py   → ui/main.json
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'ui', 'main.json')

W = H = 480

# ── 设计令牌（0xRRGGBB 十进制）─────────────────────────────
C_BG     = 0x17171B
C_SF     = 0x26262E
C_IC     = 0x31313A
C_GN     = 0x7BE0A3
C_TX     = 0xECECF0
C_SUB    = 0x9A9AA2
C_DIM    = 0x5F5F68
C_DANGER = 0xE07070
C_ON_TX  = 0x10141A
WHITE    = 0xFFFFFF

C_DEV = [0x8B9BD4, 0x7A8B5C, 0x8B6E5C]

AL_HL, AL_HC, AL_HR = 0, 1, 2          # 水平
AL_VT, AL_VC, AL_VB = 0, 4, 8          # 垂直
AL_LC = AL_HL | AL_VC                  # 左中 36
AL_CC = AL_HC | AL_VC                  # 中中 37
AL_RC = AL_HR | AL_VC                  # 右中 38
AL_LT = AL_HL | AL_VT                   # 左顶 0
AL_CT = AL_HC | AL_VT                   # 中顶 33
AL_CB = AL_HC | AL_VB                   # 中底 41

_n = {}
_id = {}


def _next(kind):
    _n[kind] = _n.get(kind, 0) + 1
    return '%s__%d' % (kind, _n[kind])


def _newid(kind):
    base = {'textview': 50000, 'button': 20000, 'window': 110000,
            'scrollwindow': 120000, 'pagewindow': 130000, 'seekbar': 40000,
            'listview': 60000, 'edittext': 51000}[kind]
    _id[kind] = _id.get(kind, 0) + 1
    return base + _id[kind]


def pos(l, t, w, h):
    return {'left': int(l), 'top': int(t), 'width': int(w), 'height': int(h)}


# ── 控件构造 ─────────────────────────────────────────────
def tv(host, caption, p, text='', size=18, color=C_TX, align=AL_LT,
       touchable=False, bold=False, bgpic=None, visible=True):
    c = {
        'id': _newid('textview'), 'caption': caption, 'position': pos(*p),
        'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                        'color3': -1, 'color4': -1},
        'fontSize': size, 'touchable': touchable, 'bold': bold, 'italic': False,
        'text': text, 'visible': visible,
        'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150, 'rollStep': 5,
        'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1},
    }
    if bgpic:
        c['backgroundPic'] = bgpic
    host[_next('textview')] = c
    return c


def btn(host, caption, p, text='', color=C_TX, color1=None, size=None,
        align=AL_CC, normal=None, pressed=None, touchable=True, visible=True):
    c = {
        'id': _newid('button'), 'caption': caption, 'position': pos(*p),
        'alignment': align, 'colorTab': {'color0': color, 'color1': color1 if color1 is not None else color,
                                        'color2': -1, 'color3': -1, 'color4': -1},
        'text': text, 'touchable': touchable, 'visible': visible,
        'picTab': {}, 'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1},
    }
    if normal:
        c['picTab'] = {'normalPic': normal, 'pressedPic': pressed or normal}
    if size:
        c['fontSize'] = size
    host[_next('button')] = c
    return c


def win(host, caption, p, bg=C_BG, visible=True, modal=False, touchable=False):
    c = {
        'id': _newid('window'), 'caption': caption, 'position': pos(*p),
        'backgroundColor': bg, 'hideTimeOut': -1, 'modal': modal,
        'touchable': touchable, 'visible': visible,
    }
    host[_next('window')] = c
    return c


def scrollwin(host, caption, p, drag=200, orientation=0, edge=1, visible=True):
    c = {
        'id': _newid('scrollwindow'), 'caption': caption, 'position': pos(*p),
        'dragMaxDis': drag, 'orientation': orientation, 'edgeEffect': edge,
        'touchable': True, 'visible': visible,
    }
    host[_next('scrollwindow')] = c
    return c


# ── 页面：主页 ────────────────────────────────────────────
DEVICES = [('客厅灯', 'dev_lamp.png'), ('卧室灯', 'dev_bed.png'), ('灯带', 'dev_strip.png')]
SCENES_DEFAULT = ['回家', '离家', '睡眠', '休闲']
# 屏保状态芯片 141px 宽有限：名字用 2 字简称
SS_NAMES = ['客厅', '卧室', '灯带']
SS_ICONS = ['ic_lamp_w20.png', 'ic_bedlamp_w20.png', 'ic_strip_w20.png']
CHIP_W, CHIP_STEP, CHIP_X0 = 84, 96, 16


def frame(w, cap):
    """屏体装饰外框（原型 .dev 的 6px #2A2A32 圆角 30 边框）——压在页面内容之上。"""
    tv(w, cap, (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/frame.png')


def bgpic_layer(host, caption, p, pic, visible=True):
    """背景图垫层（用 textview 的 backgroundPic 画，button 只做透明的触摸层）。

    原因（真机实测 2026-09-24，1.108 / easyui 2.6.0）：**button 的 picTab.normalPic 图上不了屏**
    （卡片底 #26262E / chip 底都画不出来，只有圆形图标与文字），而 textview 的 backgroundPic 正常。
    """
    tv(host, caption, p, '', 16, C_TX, AL_CC, bgpic=pic, visible=visible)


def page_home(root):
    w = win(root, 'WinHome', (0, 0, W, H), bg=C_BG, visible=True)

    tv(w, 'TextClk', (20, 20, 220, 48), '20:47', 38, C_TX, AL_LT, bold=True)
    tv(w, 'TextDate', (20, 74, 240, 26), '09月24日 星期四', 18, C_SUB, AL_LT)
    tv(w, 'TextWxTemp', (276, 24, 140, 34), '26.5°C', 26, C_TX, AL_RC, bold=True)
    tv(w, 'TextWxText', (276, 62, 140, 24), '晴 26°C', 18, C_SUB, AL_RC)

    btn(w, 'ButtonGear', (428, 18, 34, 34), '', C_GN, align=AL_CC,
        normal='images/gear_btn.png')
    tv(w, 'ImageGear', (435, 25, 20, 20), '', 16, C_GN, AL_CC, bgpic='images/ic_gear_g20.png')

    # 3 张设备卡（底图走 textview 垫层，button 只做透明触摸层）
    for i, (name, pic) in enumerate(DEVICES):
        x = 16 + i * 153
        bgpic_layer(w, 'ImageCardBg%d' % (i + 1), (x, 116, 141, 216), 'images/card.png')
        btn(w, 'ButtonDev%d' % (i + 1), (x, 116, 141, 216), '', C_TX, align=AL_CC)
        tv(w, 'ImageDev%d' % (i + 1), (x + 28, 152, 84, 84), '', 16, C_TX, AL_CC,
           bgpic='images/' + pic)
        tv(w, 'TextDevName%d' % (i + 1), (x, 250, 141, 26), name, 20, C_TX, AL_CC)
        tv(w, 'TextDevState%d' % (i + 1), (x, 278, 141, 24),
           '开启' if i < 2 else '关闭', 18, C_GN if i < 2 else C_DIM, AL_CC)

    # 情景条
    tv(w, 'TextSceneLabel', (18, 366, 200, 24), '情景模式', 18, C_SUB, AL_LT)
    strip = win(w, 'WindowSceneStrip', (0, 392, W, 44), bg=-1, visible=True)
    for i in range(8):
        cx = CHIP_X0 + i * CHIP_STEP
        vis = i < len(SCENES_DEFAULT)
        bgpic_layer(strip, 'ImageChipBg%d' % (i + 1), (cx, 0, CHIP_W, 44),
                    'images/chip.png', visible=vis)
        btn(strip, 'ButtonSceneChip%d' % (i + 1), (cx, 0, CHIP_W, 44),
            SCENES_DEFAULT[i] if vis else '',
            0xECECF0, color1=C_ON_TX, size=20, align=AL_CC, visible=vis)
    tv(w, 'ImageDot1', (228, 452, 8, 8), '', 16, C_GN, AL_CC, bgpic='images/dot_on.png',
       visible=False)   # 情景数 ≤ 4 时一屏放得下，不翻页 → 不显示页点（由 logic 按实测题数切）
    tv(w, 'ImageDot2', (240, 452, 8, 8), '', 16, C_DIM, AL_CC, bgpic='images/dot_off.png',
       visible=False)
    return w


# ── 页面：屏保 ────────────────────────────────────────────
def page_ss(root):
    w = win(root, 'WinSs', (0, 0, W, H), bg=C_BG, visible=False)
    tv(w, 'ImageSsBg', (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/ss_bg.png')
    tv(w, 'TextSsClk', (0, 86, W, 140), '19:38', 104, WHITE, AL_CC)
    tv(w, 'TextSsDate', (0, 236, W, 28), '2026年09月24日 星期四', 22, C_SUB, AL_CC)
    tv(w, 'ImageSsWxIcon', (188, 282, 22, 22), '', 16, C_GN, AL_CC, bgpic='images/ic_sun_g22.png')
    tv(w, 'TextSsWx', (216, 280, 140, 26), '晴 26', 20, C_GN, AL_HL | AL_VC)
    tv(w, 'TextSsTh', (0, 326, W, 28), '26.5°C / 58 %', 22, C_TX, AL_CC)

    for i, (name, pic) in enumerate(DEVICES):
        x = 16 + i * 153
        tv(w, 'ImageSsChip%d' % (i + 1), (x, 396, 141, 40), '', 16, C_TX, AL_CC,
           bgpic='images/ss_chip.9.png')
        tv(w, 'ImageSsDevIcon%d' % (i + 1), (x + 12, 406, 20, 20), '', 16, WHITE, AL_CC,
           bgpic='images/' + SS_ICONS[i])
        tv(w, 'TextSsDevName%d' % (i + 1), (x + 34, 404, 56, 24), SS_NAMES[i], 18, C_SUB, AL_HL | AL_VC)
        tv(w, 'TextSsDevState%d' % (i + 1), (x + 91, 404, 40, 24),
           '开' if i < 2 else '关', 18, C_GN if i < 2 else C_DIM, AL_HL | AL_VC)
    tv(w, 'TextSsHint', (0, 448, W, 24), '触摸任意处进入面板', 18, C_DIM, AL_CC)
    return w


# ── 页面：设置主页（滑动窗口）──────────────────────────────
SET_ROWS = [
    ('group', '设备', 'Device'),
    ('row', 'ButtonRowWifi', 'ic_wifi_g20.png', 'WiFi', '已连接 · 192.0.2.108'),
    ('row', 'ButtonRowMode', 'ic_refresh_g20.png', '运行模式', 'HA模式 · HA: 已连接'),
    ('row', 'ButtonRowName', 'ic_tag_g20.png', '设备名称', 'PANEL-B9D923B'),
    ('row', 'ButtonRowScenes', 'ic_sliders_g20.png', '情景模式', '4 个情景 · 可增删'),
    ('group', '屏保', 'Ss'),
    ('row', 'ButtonRowOff', 'ic_moon_g20.png', '关屏设置', '0:00-7:00 息屏 · 必选'),
    ('row', 'ButtonRowSsSet', 'ic_screens_g20.png', '屏保显示', '5 项开启 · 可增删'),
    ('row', 'ButtonRowVideo', 'ic_film_g20.png', '屏保视频', '连续轮播'),
    ('row', 'ButtonRowAlbum', 'ic_image_g20.png', '相册上传', '点按进入相册模式'),
    ('group', '系统', 'Sys'),
    ('row', 'ButtonRowVer', 'ic_info_g20.png', '版本信息', 'SmartPanel v1.0 · Z20'),
]
ROW_X, ROW_W, ROW_H, ROW_STEP = 14, 452, 50, 56
GRP_H = 28


def page_set(root, flat=False):
    w = win(root, 'WinSet', (0, 0, W, H), bg=C_BG, visible=False)
    tv(w, 'TextSetTitle', (20, 12, 200, 30), '设置', 22, C_TX, AL_LT, bold=True)
    tv(w, 'TextSetTitleEn', (20, 44, 200, 22), 'SETTINGS', 18, C_DIM, AL_LT)
    btn(w, 'ButtonSetBack', (372, 16, 90, 32), '返回 ›', C_GN, size=18, align=AL_RC)

    if flat:
        # 仅用于预览渲染：预览工具不渲染 scrollwindow 子内容，这里铺平一层（不改设备口径）
        inner = win(w, 'WindowSetList', (0, 62, W, 600), bg=-1, visible=True)
        top = 0
    else:
        # orientation：0=水平 / 1=垂直（本项目列表要竖向滑动）
        sc = scrollwin(w, 'ScrollSet', (0, 62, W, 418), drag=200, orientation=1, edge=1)
        # scrollwindow 内必须嵌 window（check_all 层级规则）
        inner = win(sc, 'WindowSetList', (0, 0, W, 600), bg=-1, visible=True)
        top = 0
    y = 4 + top
    for item in SET_ROWS:
        if item[0] == 'group':
            tv(inner, 'TextGrp' + item[2], (22, y + 4, 240, 22), item[1], 18, C_SUB, AL_LT)
            y += GRP_H
            continue
        _, cap, icon, label, value = item
        bgpic_layer(inner, cap + 'Bg', (ROW_X, y, ROW_W, ROW_H), 'images/srow.9.png')
        btn(inner, cap, (ROW_X, y, ROW_W, ROW_H), '', C_TX, align=AL_LC)
        tv(inner, cap + 'IconBg', (ROW_X + 14, y + 8, 34, 34), '', 16, C_GN, AL_CC,
           bgpic='images/sicon.9.png')
        tv(inner, cap + 'Icon', (ROW_X + 21, y + 15, 20, 20), '', 16, C_GN, AL_CC,
           bgpic='images/' + icon)
        tv(inner, cap + 'Label', (ROW_X + 61, y + 6, 300, 22), label, 18, C_TX, AL_LT)
        tv(inner, cap + 'Value', (ROW_X + 61, y + 27, 300, 20), value, 16, C_SUB, AL_LT)
        tv(inner, cap + 'Chevron', (ROW_X + 416, y + 15, 20, 20), '', 16, C_DIM, AL_CC,
           bgpic='images/ic_chr_dim20.png')
        y += ROW_STEP
    return w


def main():
    import sys
    flat = '--flat' in sys.argv
    root = {
        'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
        'resolution': {'height': H, 'width': W}, 'topmost': False,
        'position': {'height': H, 'left': 0, 'top': 0, 'width': W},
    }
    page_home(root)
    page_ss(root)
    page_set(root, flat=flat)
    out = OUT if not flat else os.path.join(ROOT, 'proto_render', 'main_flat.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(root, f, ensure_ascii=False, indent=2)
    print('written %s  (%d controls)' % (out, sum(1 for k in root if '__' in k)))


if __name__ == '__main__':
    main()
