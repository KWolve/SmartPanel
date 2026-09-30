# -*- coding: utf-8 -*-
"""SmartPanel_HA UI 生成器 -- **多 Activity 架构**（一页一 ftu/Activity，480×480，Z20）。

口径（钟工 2026-09-24 纠正）：按规范走**默认多 Activity**，不把多页塞进一个 ftu 的整屏 window；
页面之间**不互相操作控件**：内部状态走业务单例（全局共享），参数用 Intent 传递。
设计基准：smarthome_panel_product_design_spec.md + index.html 原型（480×480 1:1）
字段全集：knowledge/uicontrols/json-field-mandatory.md（每类型必写键全部显式）

本文件当前产出：
  main.json     屏保（应用入口 Activity，onStartupApp 返回 mainActivity；触摸任意处  homeActivity）
  home.json     主页（3 设备卡 + 情景条；齿轮  settingsActivity）
  settings.json 设置主页（竖向滑动窗口；行  各子页）

用法：python ui/_gen/gen_pages.py    ui/{main,home,settings}.json
"""
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT_DIR, 'ui')

W = H = 480

# ── 设计令牌（0xRRGGBB 十进制）─────────────────────────────
C_BG, C_SF, C_IC = 0x17171B, 0x26262E, 0x31313A
C_GN, C_TX, C_SUB, C_DIM = 0x7BE0A3, 0xECECF0, 0x9A9AA2, 0x5F5F68
C_ON_TX, WHITE = 0x10141A, 0xFFFFFF

AL_HL, AL_HC, AL_HR = 0, 1, 2
AL_VT, AL_VC, AL_VB = 0, 4, 8
AL_LC, AL_CC, AL_RC = AL_HL | AL_VC, AL_HC | AL_VC, AL_HR | AL_VC
AL_LT = AL_HL | AL_VT

_n, _id = {}, {}


def _next(kind):
    _n[kind] = _n.get(kind, 0) + 1
    return '%s__%d' % (kind, _n[kind])


def _newid(kind):
    base = {'textview': 50000, 'button': 20000, 'window': 110000, 'scrollwindow': 120000,
            'pagewindow': 130000, 'seekbar': 40000, 'listview': 60000, 'edittext': 51000,
            'videoview': 95000}[kind]
    _id[kind] = _id.get(kind, 0) + 1
    return base + _id[kind]


def pos(l, t, w, h):
    return {'left': int(l), 'top': int(t), 'width': int(w), 'height': int(h)}


def root_node():
    return {'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
            'resolution': {'height': H, 'width': W}, 'topmost': False,
            'position': {'height': H, 'left': 0, 'top': 0, 'width': W}}


def tv(host, caption, p, text='', size=18, color=C_TX, align=AL_LT,
       touchable=False, bold=False, bgpic=None, visible=True):
    c = {'id': _newid('textview'), 'caption': caption, 'position': pos(*p),
         'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                          'color3': -1, 'color4': -1},
         'fontSize': size, 'touchable': touchable, 'bold': bold, 'italic': False,
         'text': text, 'visible': visible, 'rollEnable': False, 'rollDirection': 1,
         'rollIntervalTime': 150, 'rollStep': 5,
         'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}
    if bgpic:
        c['backgroundPic'] = bgpic
    host[_next('textview')] = c
    return c


def btn(host, caption, p, text='', color=C_TX, color1=None, size=None,
        align=AL_CC, touchable=True, visible=True, long_to=0):
    c = {'id': _newid('button'), 'caption': caption, 'position': pos(*p), 'alignment': align,
         'colorTab': {'color0': color, 'color1': color1 if color1 is not None else color,
                      'color2': -1, 'color3': -1, 'color4': -1},
         'text': text, 'touchable': touchable, 'visible': visible, 'picTab': {},
         'longClickTimeOut': long_to if long_to else -1,
         'longClickIntervalTime': -1,
         'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}
    if size:
        c['fontSize'] = size
    host[_next('button')] = c
    return c


def edittext(host, caption, p, text='', hint='', size=18, text_type=0,
             color=C_TX, hint_color=C_DIM, bg=-1, visible=True):
    """输入框（textType 0=全文本 中文输入  弹系统键盘；拼音已由 dictPinyinPath 开启）。"""
    c = {'id': _newid('edittext'), 'caption': caption, 'position': pos(*p), 'alignment': AL_LC,
         'bgColorTab': {'color0': bg, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1},
         'bold': False, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                     'color3': -1, 'color4': -1},
         'fontSize': size, 'hintTextColor': hint_color, 'hintText': hint,
         'text': text, 'textType': text_type, 'touchable': True, 'visible': visible}
    host[_next('edittext')] = c
    return c


def win(host, caption, p, bg=-1, visible=True, modal=False, touchable=False):
    c = {'id': _newid('window'), 'caption': caption, 'position': pos(*p), 'backgroundColor': bg,
         'hideTimeOut': -1, 'modal': modal, 'touchable': touchable, 'visible': visible}
    host[_next('window')] = c
    return c


def scrollwin(host, caption, p, drag=200, orientation=1, edge=1, visible=True):
    c = {'id': _newid('scrollwindow'), 'caption': caption, 'position': pos(*p),
         'dragMaxDis': drag, 'orientation': orientation, 'edgeEffect': edge,
         'touchable': True, 'visible': visible}
    host[_next('scrollwindow')] = c
    return c


def bgpic_layer(host, caption, p, pic, visible=True):
    """背景图垫层：底图一律用 textview 的 backgroundPic 画（button 的 picTab 图在 1.108/easyui 2.6.0 上不渲染）。"""
    tv(host, caption, p, '', 16, C_TX, AL_CC, bgpic=pic, visible=visible)


def frame(w, cap):
    """屏体装饰外框（6px #2A2A32 圆角 30）--压在页面内容之上。"""
    tv(w, cap, (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/frame.png')


DEVICES = [('客厅灯', 'dev_lamp.png'), ('卧室灯', 'dev_bed.png'), ('灯带', 'dev_strip.png')]
SCENES_DEFAULT = ['回家', '离家', '睡眠', '休闲']
CHIP_W, CHIP_STEP, CHIP_X0 = 100, 108, 16


def videoview(host, caption, p, visible=True):
    """屏保视频层（字段集按 json-field-mandatory videoview：backgroundColor 0 = 实黑底）。"""
    c = {'id': _newid('videoview'), 'caption': caption, 'position': pos(*p),
         'backgroundColor': 0, 'defaultVolume': 0, 'loopPlayback': False, 'rotation': 0,
         'touchable': False, 'visible': visible}
    host[_next('videoview')] = c
    return c


# ── 屏保（main.ftu = 入口 Activity）────────────────────────
def build_ss():
    r = root_node()
    # 视频层在最底（主页也是同一路连续播放，透明浮层压在它上面）
    videoview(r, 'VideoSs', (0, 0, W, H))
    tv(r, 'ImageSsBg', (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/ss_bg.png')
    tv(r, 'TextSsClk', (0, 86, W, 140), '19:38', 104, WHITE, AL_CC)
    tv(r, 'TextSsDate', (0, 236, W, 28), '2026年09月24日 星期四', 22, C_SUB, AL_CC)
    tv(r, 'ImageSsWxIcon', (188, 282, 22, 22), '', 16, C_GN, AL_CC, bgpic='images/ic_sun_g22.png')
    tv(r, 'TextSsWx', (216, 280, 140, 26), '晴 26', 20, C_GN, AL_HL | AL_VC)
    tv(r, 'TextSsTh', (0, 326, W, 28), '26.5°C / 58 %', 22, C_TX, AL_CC)
    ss_icons = ['ic_lamp_w20.png', 'ic_bedlamp_w20.png', 'ic_strip_w20.png']
    ss_names = ['客厅', '卧室', '灯带']
    for i in range(3):
        x = 16 + i * 153
        bgpic_layer(r, 'ImageSsChip%d' % (i + 1), (x, 396, 141, 40), 'images/sschip141x40.png')
        tv(r, 'ImageSsDevIcon%d' % (i + 1), (x + 12, 406, 20, 20), '', 16, WHITE, AL_CC,
           bgpic='images/' + ss_icons[i])
        tv(r, 'TextSsDevName%d' % (i + 1), (x + 34, 404, 56, 24), ss_names[i], 18, C_SUB,
           AL_HL | AL_VC)
        tv(r, 'TextSsDevState%d' % (i + 1), (x + 91, 404, 40, 24), '开' if i < 2 else '关', 18,
           C_GN if i < 2 else C_DIM, AL_HL | AL_VC)
    tv(r, 'TextSsHint', (0, 448, W, 24), '触摸任意处进入面板', 18, C_DIM, AL_CC)
    # 整屏触摸：点任意处  homeActivity（onmainActivityTouchEvent）
    return r


# ── 主页（home.ftu）────────────────────────────────────────
def build_home():
    r = root_node()
    tv(r, 'TextClk', (20, 20, 220, 48), '20:47', 38, C_TX, AL_LT, bold=True)
    tv(r, 'TextDate', (20, 74, 240, 26), '09月24日 星期四', 18, C_SUB, AL_LT)
    tv(r, 'TextWxTemp', (276, 24, 140, 34), '26.5°C', 26, C_TX, AL_RC, bold=True)
    tv(r, 'TextWxText', (276, 62, 140, 24), '晴 26°C', 18, C_SUB, AL_RC)

    bgpic_layer(r, 'ImageGearBg', (428, 18, 34, 34), 'images/gear_btn.png')
    btn(r, 'ButtonGear', (428, 18, 34, 34), '', C_GN)
    tv(r, 'ImageGear', (435, 25, 20, 20), '', 16, C_GN, AL_CC, bgpic='images/ic_gear_g20.png')

    for i, (name, pic) in enumerate(DEVICES):
        x = 16 + i * 153
        bgpic_layer(r, 'ImageCardBg%d' % (i + 1), (x, 116, 141, 216), 'images/card.png')
        btn(r, 'ButtonDev%d' % (i + 1), (x, 116, 141, 216), '', C_TX, long_to=600)
        tv(r, 'ImageDev%d' % (i + 1), (x + 28, 152, 84, 84), '', 16, C_TX, AL_CC,
           bgpic='images/' + pic)
        tv(r, 'TextDevName%d' % (i + 1), (x, 250, 141, 26), name, 20, C_TX, AL_CC)
        tv(r, 'TextDevState%d' % (i + 1), (x, 278, 141, 24), '开启' if i < 2 else '关闭', 18,
           C_GN if i < 2 else C_DIM, AL_CC)

    tv(r, 'TextSceneLabel', (18, 366, 200, 24), '情景模式', 18, C_SUB, AL_LT)
    strip = win(r, 'WindowSceneStrip', (0, 388, W, 60), bg=-1, visible=True)
    for i in range(8):
        cx = CHIP_X0 + i * CHIP_STEP
        vis = i < len(SCENES_DEFAULT)
        bgpic_layer(strip, 'ImageChipBg%d' % (i + 1), (cx, 0, CHIP_W, 60), 'images/chip.png', vis)
        btn(strip, 'ButtonSceneChip%d' % (i + 1), (cx, 0, CHIP_W, 60), '', C_TX, size=20, visible=vis)
        # 文字用独立 textview（touchPass）：运行时能自由切高对比字色（button 的字色只能靠 colorTab）
        tv(strip, 'TextChip%d' % (i + 1), (cx, 0, CHIP_W, 60),
           SCENES_DEFAULT[i] if vis else '', 20, C_TX, AL_CC, visible=vis)
    tv(r, 'ImageDot1', (228, 452, 8, 8), '', 16, C_GN, AL_CC, bgpic='images/dot_on.png',
       visible=False)
    tv(r, 'ImageDot2', (240, 452, 8, 8), '', 16, C_DIM, AL_CC, bgpic='images/dot_off.png',
       visible=False)

    # 情景编辑模态框（同一 Activity 内的弹窗；根窗口 modal，点遮罩关闭）
    md = win(r, 'WindowSceneEdit', (0, 0, W, H), bg=-1, visible=False, modal=True)
    tv(md, 'ImageDim', (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/dim.png')
    bgpic_layer(md, 'ImageMbox', (68, 120, 344, 200), 'images/mbox344.png')
    btn(md, 'ButtonEditPrev', (76, 132, 44, 36), '<', C_GN, size=22)
    tv(md, 'TextEditScene', (120, 132, 240, 36), '回家模式', 22, C_TX, AL_CC, bold=True)
    btn(md, 'ButtonEditNext', (360, 132, 44, 36), '>', C_GN, size=22)
    tv(md, 'TextEditSub', (86, 176, 308, 24), '本机 · 3 路开关', 18, C_SUB, AL_LT)
    for i in range(3):
        x = 86 + i * 104
        bgpic_layer(md, 'ImageMswBg%d' % (i + 1), (x, 204, 96, 40), 'images/msw96x40.png')
        btn(md, 'ButtonEditSw%d' % (i + 1), (x, 204, 96, 40), '灯 %d' % (i + 1), C_SUB, size=18)
    bgpic_layer(md, 'ImageEditSaveBg', (86, 258, 308, 46), 'images/btn_primary308x46.png')
    btn(md, 'ButtonEditSave', (86, 258, 308, 46), '保存', C_ON_TX, size=20)

    # 开关按键重命名模态框（长按设备卡弹出；输入框 textType=0  系统键盘 + 拼音）
    rn = win(r, 'WindowRename', (0, 0, W, H), bg=-1, visible=False, modal=True)
    tv(rn, 'ImageRenameDim', (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/dim.png')
    bgpic_layer(rn, 'ImageRenameBox', (56, 130, 368, 200), 'images/mbox368.png')
    tv(rn, 'TextRenameTitle', (76, 146, 328, 30), '开关名称', 22, C_TX, AL_LT, bold=True)
    tv(rn, 'TextRenameHint', (76, 178, 328, 24), '最长 8 个字 · 切换语言自动恢复', 18, C_SUB, AL_LT)
    edittext(rn, 'EditRename', (76, 210, 328, 46), '', '输入名称', size=20)
    bgpic_layer(rn, 'ImageRenameOkBg', (76, 272, 152, 44), 'images/btn_primary152x44.png')
    btn(rn, 'ButtonRenameOk', (76, 272, 152, 44), '确定', C_ON_TX, size=20)
    bgpic_layer(rn, 'ImageRenameCancelBg', (252, 272, 152, 44), 'images/msw152x44.png')
    btn(rn, 'ButtonRenameCancel', (252, 272, 152, 44), '取消', C_TX, size=20)
    return r


# ── 设置主页（settings.ftu）────────────────────────────────
SET_ROWS = [
    ('group', '设备', 'Device'),
    ('row', 'ButtonRowWifi', 'ic_wifi_g20.png', 'WiFi', '已连接 · --'),
    ('row', 'ButtonRowMode', 'ic_refresh_g20.png', '运行模式', 'HA模式 · HA: 已连接'),
    ('row', 'ButtonRowName', 'ic_tag_g20.png', '设备名称', 'PANEL-B9D923B'),
    ('row', 'ButtonRowScenes', 'ic_sliders_g20.png', '情景模式', '4 个情景 · 可增删'),
    ('row', 'ButtonRowBright', 'ic_bright_g20.png', '屏幕亮度', '工作 80% · 屏保 30%'),
    ('group', '屏保', 'Ss'),
    ('row', 'ButtonRowOff', 'ic_moon_g20.png', '关屏设置', '0:00-7:00 息屏 · 必选'),
    ('row', 'ButtonRowSsSet', 'ic_screens_g20.png', '屏保显示', '5 项开启 · 可增删'),
    ('row', 'ButtonRowVideo', 'ic_film_g20.png', '屏保视频', '连续轮播'),
    ('row', 'ButtonRowAlbum', 'ic_image_g20.png', '相册上传', '点按进入相册模式'),
    ('group', '系统', 'Sys'),
    ('row', 'ButtonRowVer', 'ic_info_g20.png', '版本信息', 'SmartPanel v1.0 · Z20'),
]
ROW_X, ROW_W, ROW_H, ROW_STEP, GRP_H = 14, 452, 50, 56, 28


def build_settings():
    r = root_node()
    tv(r, 'TextSetTitle', (20, 12, 200, 30), '设置', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextSetTitleEn', (20, 44, 200, 22), 'SETTINGS', 18, C_DIM, AL_LT)
    btn(r, 'ButtonSetBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    # scrollwindow 用法：内嵌 window 高度 = **内容实际总高**（算准！之前写 600 < 实际 644  底部两行被截）
    sc = scrollwin(r, 'ScrollSet', (0, 62, W, 418), drag=60, orientation=1, edge=1)
    content_h = 8
    for it in SET_ROWS:
        content_h += GRP_H if it[0] == 'group' else ROW_STEP
    inner = win(sc, 'WindowSetList1', (0, 0, W, content_h), bg=-1, visible=True)
    y = 4
    for item in SET_ROWS:
        if item[0] == 'group':
            tv(inner, 'TextGrp' + item[2], (22, y + 4, 240, 22), item[1], 18, C_SUB, AL_LT)
            y += GRP_H
            continue
        _, cap, icon, label, value = item
        bgpic_layer(inner, cap + 'Bg', (ROW_X, y, ROW_W, ROW_H), 'images/srow452x50.png')
        btn(inner, cap, (ROW_X, y, ROW_W, ROW_H), '', C_TX, align=AL_LC)
        tv(inner, cap + 'IconBg', (ROW_X + 14, y + 8, 34, 34), '', 16, C_GN, AL_CC,
           bgpic='images/sicon34x34.png')
        tv(inner, cap + 'Icon', (ROW_X + 21, y + 15, 20, 20), '', 16, C_GN, AL_CC,
           bgpic='images/' + icon)
        tv(inner, cap + 'Label', (ROW_X + 61, y + 6, 300, 22), label, 18, C_TX, AL_LT)
        tv(inner, cap + 'Value', (ROW_X + 61, y + 27, 300, 20), value, 16, C_SUB, AL_LT)
        tv(inner, cap + 'Chevron', (ROW_X + 416, y + 15, 20, 20), '', 16, C_DIM, AL_CC,
           bgpic='images/ic_chr_dim20.png')
        y += ROW_STEP
    return r


def seekbar(host, caption, p, def_progress=50, visible=True):
    """亮度滑条（字段集按 basedemo SeekBarDemo 实测：id 90000+ / orientation 0=水平）。"""
    c = {'id': _newid('seekbar'), 'caption': caption, 'position': pos(*p),
         'backgroundColor': -1, 'backgroundPic': 'images/seekbar_bg.png',
         'progressPic': 'images/seekbar_prog.png', 'defProgress': def_progress, 'max': 100,
         'orientation': 0, 'touchable': True, 'visible': visible,
         'thumb': {'normalPic': 'images/seekbar_thumb.png',
                   'size': {'width': 26, 'height': 26}}}
    host[_next('seekbar')] = c
    return c


# ── 屏幕亮度（brightness.ftu）──────────────────────────────
def build_brightness():
    r = root_node()
    tv(r, 'TextBrTitle', (20, 12, 240, 30), '屏幕亮度', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextBrTitleEn', (20, 44, 240, 22), 'BRIGHTNESS', 18, C_DIM, AL_LT)
    btn(r, 'ButtonBrBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    tv(r, 'TextBrWorkLabel', (20, 104, 300, 26), '工作页面亮度', 18, C_TX, AL_LT)
    tv(r, 'TextBrWorkValue', (330, 100, 130, 30), '80%', 20, C_GN, AL_RC, bold=True)
    seekbar(r, 'SeekBrWork', (20, 136, 440, 34), 80)

    tv(r, 'TextBrSsLabel', (20, 214, 300, 26), '屏保亮度', 18, C_TX, AL_LT)
    tv(r, 'TextBrSsValue', (330, 210, 130, 30), '30%', 20, C_GN, AL_RC, bold=True)
    seekbar(r, 'SeekBrSs', (20, 246, 440, 34), 30)

    tv(r, 'TextBrHint1', (20, 296, 440, 24), '工作亮度：主页/设置等页面使用', 16, C_SUB, AL_LT)
    tv(r, 'TextBrHint2', (20, 322, 440, 24), '屏保亮度：进入屏保后自动切换', 16, C_SUB, AL_LT)
    bgpic_layer(r, 'ImageBrSaveBg', (20, 366, 440, 48), 'images/btn_primary440x48.png')
    btn(r, 'ButtonBrSave', (20, 366, 440, 48), '保存', C_ON_TX, size=20)
    return r


# ── 屏保视频（video.ftu）──────────────────────────────────
VIDEO_ROWS = 12
INT_LABELS = ['连续', '1h', '2h', '6h', '12h', '每天']


def build_video():
    r = root_node()
    tv(r, 'TextVidTitle', (20, 12, 240, 30), '屏保视频', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextVidTitleEn', (20, 44, 240, 22), 'SCREENSAVER', 18, C_DIM, AL_LT)
    btn(r, 'ButtonVidBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    # 素材列表（12 行；名称/选中状态运行时从数据分区扫 + /data 里的选中清单决定）
    tv(r, 'TextVidListHint', (20, 62, 440, 24), '素材列表（点选/取消，可多选）', 18, C_SUB, AL_LT)
    sc = scrollwin(r, 'ScrollVid', (0, 88, W, 300), drag=60, orientation=1, edge=1)
    inner = win(sc, 'WindowVidList', (0, 0, W, VIDEO_ROWS * 42 + 8), bg=-1, visible=True)
    for i in range(VIDEO_ROWS):
        y = i * 42
        bgpic_layer(inner, 'ImageVidRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')
        btn(inner, 'ButtonVidRow%d' % (i + 1), (14, y, 452, 38), '', C_TX, align=AL_LC)
        tv(inner, 'TextVidRowName%d' % (i + 1), (34, y + 8, 340, 22), '', 18, C_TX, AL_LT)
        tv(inner, 'ImageVidRowChk%d' % (i + 1), (424, y + 9, 20, 20), '', 16, C_GN, AL_CC,
           bgpic='images/ic_check_g20.png', visible=False)

    tv(r, 'TextVidIntLabel', (20, 398, 440, 24), '轮播间隔', 18, C_SUB, AL_LT)
    for i in range(6):
        x = 14 + i * 76
        bgpic_layer(r, 'ImageVidIntBg%d' % (i + 1), (x, 424, 68, 44), 'images/chip68x44.png')
        btn(r, 'ButtonVidInt%d' % (i + 1), (x, 424, 68, 44), '', C_TX, size=18)
        tv(r, 'TextVidInt%d' % (i + 1), (x, 424, 68, 44), INT_LABELS[i], 18, C_TX, AL_CC)
    return r


ALBUM_ROWS = [
    ('TextAlStatus', '等待小程序连接...'),
    ('TextAlPeer', '设备：-'),
    ('TextAlFile', '最近接收：-'),
    ('TextAlCount', '已接收：0 个文件'),
]


def build_album():
    """相册上传（小程序传图/视频）：本页只做「接收状态 + 结果」展示，传输在 mp_transfer 里。"""
    r = root_node()
    tv(r, 'TextAlTitle', (20, 12, 240, 30), '相册上传', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextAlTitleEn', (20, 44, 300, 22), 'ALBUM UPLOAD', 18, C_DIM, AL_LT)
    btn(r, 'ButtonAlBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    for i, (cap, text) in enumerate(ALBUM_ROWS):
        y = 80 + i * 42
        bgpic_layer(r, 'ImageAlRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')
        tv(r, cap, (30, y + 8, 420, 22), text, 18, C_TX, AL_LT)

    tv(r, 'TextAlHint1', (20, 254, 440, 22), '手机微信打开小程序，连接同一 WiFi', 16, C_SUB, AL_LT)
    tv(r, 'TextAlHint2', (20, 280, 440, 22), '选择照片或视频上传，自动保存到面板', 16, C_SUB, AL_LT)
    tv(r, 'TextAlHint3', (20, 306, 440, 22), '保存目录：/mnt/sdnand/album', 16, C_DIM, AL_LT)

    # 重新广播：手机搜不到设备时点一下，重启 UDP 广播 + TCP 接收
    bgpic_layer(r, 'ImageAlChipBg', (14, 350, 152, 44), 'images/btn_primary152x44.png')
    btn(r, 'ButtonAlReboot', (14, 350, 152, 44), '重新广播', 0x10141A, size=18)
    tv(r, 'TextAlChip', (14, 350, 152, 44), '重新广播', 18, 0x10141A, AL_CC)
    return r


SS_ITEMS = [('time', '时间'), ('date', '日期'), ('temphum', '温湿度'),
            ('weather', '天气'), ('statusbar', '设备状态条')]


def build_ssset():
    """屏保显示：5 项显隐开关（点行切换，状态存 /data）+ 位置编辑提示。"""
    r = root_node()
    tv(r, 'TextSsSetTitle', (20, 12, 260, 30), '屏保显示', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextSsSetTitleEn', (20, 44, 300, 22), 'SCREENSAVER ITEMS', 18, C_DIM, AL_LT)
    btn(r, 'ButtonSsSetBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    for i, (key, label) in enumerate(SS_ITEMS):
        y = 84 + i * 52
        bgpic_layer(r, 'ImageSsSetRowBg%d' % (i + 1), (14, y, 452, 38), 'images/srow452x38.png')
        tv(r, 'TextSsSetRowLabel%d' % (i + 1), (34, y + 8, 260, 22), label, 18, C_TX, AL_LT)
        bgpic_layer(r, 'ImageSsSetChip%d' % (i + 1), (378, y - 3, 68, 44), 'images/chip68x44.png')
        btn(r, 'ButtonSsSetRow%d' % (i + 1), (14, y, 452, 38), '', C_TX, align=AL_LC)
        tv(r, 'TextSsSetRowValue%d' % (i + 1), (378, y - 3, 68, 44), '显示', 18, C_TX, AL_CC)

    tv(r, 'TextSsSetHint1', (20, 360, 440, 22), '点行切换显示/隐藏（立即生效并存 /data）', 16, C_SUB, AL_LT)
    tv(r, 'TextSsSetHint2', (20, 386, 440, 22), '位置编辑：后续版本支持拖动调整', 16, C_DIM, AL_LT)
    return r


# ── 关屏设置（off.ftu）────────────────────────────────────
def seekbar23(host, caption, p, def_hour=0):
    """整点滑条（0..23，绿色圆形滑块；字段集同亮度页 seekbar，仅 max 改 23）。"""
    c = {'id': _newid('seekbar'), 'caption': caption, 'position': pos(*p),
         'backgroundColor': -1, 'backgroundPic': 'images/seekbar_bg.png',
         'progressPic': 'images/seekbar_prog.png', 'defProgress': def_hour, 'max': 23,
         'orientation': 0, 'touchable': True, 'visible': True,
         'thumb': {'normalPic': 'images/seekbar_thumb.png',
                   'size': {'width': 26, 'height': 26}}}
    host[_next('seekbar')] = c
    return c


def build_off():
    """关屏设置（设计说明书 3.4.4）：启用开关 + 起止整点滑块 + 先后校验 + 摘要 + 保存。"""
    r = root_node()
    tv(r, 'TextOffTitle', (20, 12, 260, 30), '关屏设置', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextOffTitleEn', (20, 44, 300, 22), 'SCREEN OFF', 18, C_DIM, AL_LT)
    btn(r, 'ButtonOffBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    # 启用关屏（行 + toggle chip）
    bgpic_layer(r, 'ImageOffRowBg1', (14, 80, 452, 38), 'images/srow452x38.png')
    tv(r, 'TextOffEnLabel', (34, 88, 300, 22), '启用关屏时段', 18, C_TX, AL_LT)
    bgpic_layer(r, 'ImageOffChip1', (378, 77, 68, 44), 'images/chip68x44_hl.png')
    btn(r, 'ButtonOffRow1', (14, 80, 452, 38), '', C_TX, align=AL_LC)
    tv(r, 'TextOffEnValue', (378, 77, 68, 44), '开启', 18, 0x10141A, AL_CC)

    # 关屏开始时间
    tv(r, 'TextOffStartLabel', (20, 148, 300, 26), '关屏开始时间', 18, C_TX, AL_LT)
    tv(r, 'TextOffStartValue', (330, 144, 130, 30), '22:00', 20, C_GN, AL_RC, bold=True)
    seekbar23(r, 'SeekOffStart', (20, 180, 440, 34), 0)

    # 关屏结束时间
    tv(r, 'TextOffEndLabel', (20, 240, 300, 26), '关屏结束时间', 18, C_TX, AL_LT)
    tv(r, 'TextOffEndValue', (330, 236, 130, 30), '07:00', 20, C_GN, AL_RC, bold=True)
    seekbar23(r, 'SeekOffEnd', (20, 272, 440, 34), 7)

    tv(r, 'TextOffSummary', (20, 322, 440, 26), '每天 0:00 - 7:00 息屏 · 其他时间进入屏保',
       18, C_SUB, AL_LT)
    tv(r, 'TextOffHint', (20, 352, 440, 22), '拖动滑块调整整点时间，支持跨零点',
       16, C_DIM, AL_LT)
    tv(r, 'TextOffErr', (20, 378, 440, 22), '', 16, 0xE07070, AL_LT)

    bgpic_layer(r, 'ImageOffSaveBg', (20, 408, 440, 48), 'images/btn_primary440x48.png')
    btn(r, 'ButtonOffSave', (20, 408, 440, 48), '保存', C_ON_TX, size=20)
    return r


# ── 运行模式（mode.ftu）────────────────────────────────────
# 三张单选卡（HA / 本地主机 / 本地从机）+ 从机主机 IP 输入 + 保存。
# 卡片用 card.png / card_hl.png（141x216，与 home 设备卡同一套"绿卡=选中"语言），
# 选中卡右上角显 ic_check_g20.png 对勾；卡片说明按 16px 拆行（每行 <= 6 字宽，防截断）。
MODE_CARDS = [
    ('HA 模式', ['订阅 HA', '标准接入', 'discovery']),
    ('本地主机', ['内嵌 Broker', '管理子设备', '与情景联动']),
    ('本地从机', ['接入同网段', '主机接收', '情景联动']),
]


def build_mode():
    r = root_node()
    tv(r, 'TextModeTitle', (20, 12, 240, 30), '运行模式', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextModeTitleEn', (20, 44, 240, 22), 'RUN MODE', 18, C_DIM, AL_LT)
    btn(r, 'ButtonModeBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)

    for i, (name, lines) in enumerate(MODE_CARDS):
        x = 16 + i * 153
        bgpic_layer(r, 'ImageModeCardBg%d' % (i + 1), (x, 78, 141, 216), 'images/card.png')
        btn(r, 'ButtonModeCard%d' % (i + 1), (x, 78, 141, 216), '', C_TX)
        tv(r, 'ImageModeCardChk%d' % (i + 1), (x + 111, 86, 20, 20), '', 16, C_GN, AL_CC,
           bgpic='images/ic_check_g20.png', visible=(i == 0))
        tv(r, 'TextModeCardName%d' % (i + 1), (x, 174, 141, 28), name, 20, C_TX, AL_CC, bold=True)
        for j, line in enumerate(lines):
            tv(r, 'TextModeCardDesc%d%s' % (i + 1, 'abc'[j]), (x + 8, 208 + j * 20, 125, 20),
               line, 16, C_SUB, AL_CC)

    tv(r, 'TextModeIpLabel', (14, 302, 200, 24), '主机 IP', 18, C_SUB, AL_LT)
    tv(r, 'TextModeIpHint', (250, 302, 216, 24), '仅本地从机填', 16, C_DIM, AL_RC)
    bgpic_layer(r, 'ImageModeIpBg', (14, 326, 452, 38), 'images/srow452x38.png')
    edittext(r, 'EditModeIp', (30, 330, 420, 30), '', '输入主机 IP', size=18)
    tv(r, 'TextModeErr', (14, 372, 452, 22), '', 16, 0xE07070, AL_LT)
    bgpic_layer(r, 'ImageModeSaveBg', (20, 416, 440, 48), 'images/btn_primary440x48.png')
    btn(r, 'ButtonModeSave', (20, 416, 440, 48), '保存', C_ON_TX, size=20)
    return r


# ── 情景模式（scenes.ftu）──────────────────────────────────
# 已定义情景列表（最多 8 行，可滚动）+ 每行右侧删除按钮 + 新增情景（输入 + 添加）+ 删确认弹窗。
SCENE_ROW_MAX = 8
SCENE_ROW_STEP = 56


def build_scenes():
    r = root_node()
    tv(r, 'TextScenesTitle', (20, 12, 240, 30), '情景模式', 22, C_TX, AL_LT, bold=True)
    tv(r, 'TextScenesTitleEn', (20, 44, 240, 22), 'SCENES', 18, C_DIM, AL_LT)
    btn(r, 'ButtonScenesBack', (372, 16, 90, 32), '返回 >', C_GN, size=18, align=AL_RC)
    tv(r, 'TextScenesListLabel', (20, 62, 300, 24), '已定义情景 最多 8 个', 18, C_SUB, AL_LT)

    sc = scrollwin(r, 'ScrollScenes', (0, 88, W, 220), drag=60, orientation=1, edge=1)
    inner = win(sc, 'WindowScenesList', (0, 0, W, SCENE_ROW_MAX * SCENE_ROW_STEP + 8),
                bg=-1, visible=True)
    for i in range(SCENE_ROW_MAX):
        y = i * SCENE_ROW_STEP
        bgpic_layer(inner, 'ImageSceneRowBg%d' % (i + 1), (14, y, 452, 50),
                    'images/srow452x50.png')
        tv(inner, 'TextSceneRowName%d' % (i + 1), (34, y + 6, 340, 22), '', 18, C_TX, AL_LT)
        tv(inner, 'TextSceneRowDesc%d' % (i + 1), (34, y + 27, 340, 20), '', 16, C_SUB, AL_LT)
        btn(inner, 'ButtonSceneDel%d' % (i + 1), (410, y + 8, 34, 34), '', C_TX)
        tv(inner, 'ImageSceneDelIcon%d' % (i + 1), (417, y + 15, 20, 20), '', 16, C_TX, AL_CC,
           bgpic='images/ic_close_r20.png')

    tv(r, 'TextScenesAddLabel', (20, 314, 200, 24), '新增情景', 18, C_SUB, AL_LT)
    bgpic_layer(r, 'ImageSceneAddBg', (14, 340, 452, 38), 'images/srow452x38.png')
    edittext(r, 'EditSceneAdd', (30, 344, 250, 30), '', '输入情景名 最多6字', size=18)
    bgpic_layer(r, 'ImageSceneAddBtnBg', (318, 337, 152, 44), 'images/btn_primary152x44.png')
    btn(r, 'ButtonSceneAdd', (318, 337, 152, 44), '添加', C_ON_TX, size=20)
    tv(r, 'TextSceneErr', (20, 392, 440, 22), '', 16, 0xE07070, AL_LT)
    tv(r, 'TextScenesHint', (20, 418, 440, 22), '点右侧按钮删除, 需二次确认', 16, C_DIM, AL_LT)

    # 删除二次确认（同页模态；根窗口 touchable=false + modal=true）
    md = win(r, 'WindowSceneDel', (0, 0, W, H), bg=-1, visible=False, modal=True)
    tv(md, 'ImageSceneDelDim', (0, 0, W, H), '', 16, C_TX, AL_CC, bgpic='images/dim.png')
    bgpic_layer(md, 'ImageSceneDelBox', (56, 140, 368, 200), 'images/mbox368.png')
    tv(md, 'TextSceneDelTitle', (76, 158, 328, 30), '删除情景', 22, C_TX, AL_LT, bold=True)
    tv(md, 'TextSceneDelSub', (76, 194, 328, 24), '确认删除该情景', 18, C_SUB, AL_LT)
    tv(md, 'TextSceneDelName', (76, 224, 328, 24), '', 18, C_TX, AL_LT)
    bgpic_layer(md, 'ImageSceneDelOkBg', (76, 272, 152, 44), 'images/btn_primary152x44.png')
    btn(md, 'ButtonSceneDelOk', (76, 272, 152, 44), '确定', C_ON_TX, size=20)
    bgpic_layer(md, 'ImageSceneDelCancelBg', (252, 272, 152, 44), 'images/msw152x44.png')
    btn(md, 'ButtonSceneDelCancel', (252, 272, 152, 44), '取消', C_TX, size=20)
    return r


PAGES = [('main.json', build_ss), ('home.json', build_home), ('settings.json', build_settings),
         ('brightness.json', build_brightness), ('video.json', build_video),
         ('album.json', build_album), ('ssset.json', build_ssset), ('off.json', build_off)]


def main():
    for name, fn in PAGES:
        _n.clear()
        _id.clear()
        doc = fn()
        p = os.path.join(UI, name)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print('written %-14s controls=%d' % (name, sum(1 for k in doc if '__' in k)))


if __name__ == '__main__':
    main()
