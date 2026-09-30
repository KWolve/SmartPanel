# -*- coding: utf-8 -*-
"""多屏拼接 v1：① 生成 ui/wall.json（设置子页）② 给 settings.json 追加「多屏拼接」入口行
规范沿用现有：行 452x46（背景框比内容上下各高 1px 的口径用 srow452x46.png）、
每行 = 背景(textview) + 行按钮(button) + 标签(textview) + 值(textview) + 箭头(textview)。
用法：python ui/_gen/gen_wall.py
"""
import glob
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')

C_BG, C_CARD, C_IC, C_GN = 0x17171B, 0x26262E, 0x31313A, 0x7BE0A3
C_TX, C_SUB, C_DIM = 0xECECF0, 0x9AA0A6, 0x5F5F68
AL_LT, AL_CC, AL_RC = 0, 5, 6


def max_ids():
    m = {'textview__': 0, 'button__': 0}
    for p in glob.glob(os.path.join(UI, '*.json')):
        d = json.load(io.open(p, encoding='utf-8'))

        def walk(o):
            for k, v in o.items():
                if isinstance(v, dict):
                    for pre in m:
                        if k.startswith(pre) and v.get('id', 0) > m[pre]:
                            m[pre] = v['id']
                    walk(v)
                elif isinstance(v, list):
                    for x in v:
                        walk(x)
        walk(d)
    return m


class Gen(object):
    def __init__(self):
        self.seq = {}
        self.mx = max_ids()

    def _key(self, kind):
        self.seq[kind] = self.seq.get(kind, 0) + 1
        return '%s__%d' % (kind, self.seq[kind])

    def _id(self, kind):
        pre = kind + '__'
        self.mx[pre] = self.mx.get(pre, 0) + 1
        return self.mx[pre]

    def tv(self, host, cap, l, t, w, h, size, color, align, text='', pic=None, visible=True):
        c = {'id': self._id('textview'), 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                              'color3': -1, 'color4': -1},
             'fontSize': size, 'touchable': False, 'bold': False, 'italic': False,
             'text': text, 'visible': visible, 'rollEnable': False, 'rollDirection': 1,
             'rollIntervalTime': 150, 'rollStep': 5,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1}}
        if pic:
            c['backgroundPic'] = pic
        host[self._key('textview')] = c
        return c

    def btn(self, host, cap, l, t, w, h, text='', color=C_TX, size=18, align=AL_CC, pic=None):
        c = {'id': self._id('button'), 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': align, 'colorTab': {'color0': color, 'color1': color, 'color2': -1,
                                              'color3': -1, 'color4': -1},
             'text': text, 'touchable': True, 'visible': True, 'picTab': {},
             'longClickTimeOut': -1, 'longClickIntervalTime': -1, 'fontSize': size,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1}}
        if pic:
            c['backgroundPic'] = pic
        host[self._key('button')] = c
        return c


def gen_wall_page():
    g = Gen()
    r = {'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
         'resolution': {'height': 480, 'width': 480}, 'topmost': False,
         'position': {'height': 480, 'left': 0, 'top': 0, 'width': 480}}
    g.tv(r, 'TextWallTitle', 20, 12, 260, 30, 22, C_TX, AL_LT, '多屏拼接')
    g.tv(r, 'TextWallTitleEn', 20, 44, 320, 22, 15, C_DIM, AL_LT, 'MULTI-PANEL WALL')
    g.btn(r, 'ButtonWallBack', 372, 16, 90, 32, '返回 >', C_GN, 18, AL_RC)

    rows = [('拼接联动', '开启'), ('组名', 'zksw-wall'), ('本机序号', '1 / 2'),
            ('排布', '1x2'), ('角色', '主机'), ('片段时长', '12.0 s')]
    tops = [72, 124, 176, 228, 280, 332]
    for i, ((lab, val), top) in enumerate(zip(rows, tops), 1):
        g.tv(r, 'ImageWallRowBg%d' % i, 14, top, 452, 46, 16, C_TX, AL_CC, '',
             'images/srow452x46.png')
        g.btn(r, 'ButtonWallRow%d' % i, 14, top, 452, 46, '')
        g.tv(r, 'TextWallRowLabel%d' % i, 30, top + 13, 240, 22, 18, C_TX, AL_LT, lab)
        g.tv(r, 'TextWallRowValue%d' % i, 240, top + 13, 190, 22, 17, C_GN, AL_RC, val,
             None)
    g.tv(r, 'ImageWallStatusBg', 14, 388, 452, 44, 16, C_TX, AL_CC, '',
         'images/srow452x46.png')
    g.tv(r, 'TextWallStatus', 30, 399, 420, 22, 16, C_SUB, AL_LT, '状态：未开启')
    g.tv(r, 'ImageWallSaveBg', 14, 440, 214, 32, 16, C_TX, AL_CC, '',
         'images/af_btn216x48.png')
    g.btn(r, 'ButtonWallSave', 14, 440, 214, 32, '保存', C_TX, 17, AL_CC)
    g.tv(r, 'ImageWallHintBg', 252, 440, 214, 32, 16, C_TX, AL_CC, '',
         'images/af_btn216x48.png')
    g.btn(r, 'ButtonWallBack2', 252, 440, 214, 32, '返回', C_TX, 17, AL_CC)

    json.dump(r, io.open(os.path.join(UI, 'wall.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('wall.json 生成，控件数 %d' % sum(1 for k in r if '__' in k))


def add_settings_entry():
    p = os.path.join(UI, 'settings.json')
    d = json.load(io.open(p, encoding='utf-8'))
    ids = max_ids()

    # 找滚动容器与最后一行
    scroll = None
    last_top = 0
    row_tops = []

    def walk(o, parent=None):
        nonlocal scroll, last_top
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, dict):
                    cap = str(v.get('caption', ''))
                    if k == 'scrollwindow__1':
                        scroll = v
                    if cap.startswith('ButtonRow') and cap.endswith('Bg'):
                        row_tops.append(v['position']['top'])
                    walk(v, v)
                elif isinstance(v, list):
                    for x in v:
                        walk(x, o)
        elif isinstance(o, list):
            for x in o:
                walk(x, parent)

    walk(d)
    if not row_tops:
        print('! 没找到现有行，放弃加行')
        return
    last_top = max(row_tops)
    new_top = last_top + 56                      # 与现有行距一致

    def tv(cap, l, t, w, h, size, color, align, text='', pic=None):
        ids['textview__'] += 1
        c = {'id': ids['textview__'], 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                              'color3': -1, 'color4': -1},
             'fontSize': size, 'touchable': False, 'bold': False, 'italic': False,
             'text': text, 'visible': True, 'rollEnable': False, 'rollDirection': 1,
             'rollIntervalTime': 150, 'rollStep': 5,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1}}
        if pic:
            c['backgroundPic'] = pic
        return c

    def btn(cap, l, t, w, h):
        ids['button__'] += 1
        return {'id': ids['button__'], 'caption': cap,
                'position': {'left': l, 'top': t, 'width': w, 'height': h},
                'alignment': AL_CC, 'colorTab': {'color0': C_TX, 'color1': C_TX,
                                                 'color2': -1, 'color3': -1, 'color4': -1},
                'text': '', 'touchable': True, 'visible': True, 'picTab': {},
                'longClickTimeOut': -1, 'longClickIntervalTime': -1,
                'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                               'color4': -1}}

    host = scroll if scroll is not None else d
    host['textview__wall_bg'] = tv('ImageRowWallBg', 20, new_top, 440, 50, 16, C_TX,
                                   AL_CC, '', 'images/srow452x46.png')
    host['button__wall'] = btn('ButtonRowWall', 20, new_top, 440, 50)
    host['textview__wall_lab'] = tv('TextRowWallLabel', 34, new_top + 14, 300, 22, 18,
                                    C_TX, AL_LT, '多屏拼接')
    host['textview__wall_val'] = tv('TextRowWallValue', 300, new_top + 14, 120, 22, 16,
                                    C_SUB, AL_RC, '已关闭')
    host['textview__wall_chev'] = tv('TextRowWallChevron', 424, new_top + 15, 20, 20, 16,
                                     C_DIM, AL_RC, '>')

    json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('settings.json 追加「多屏拼接」行 @top=%d（上一行 %d）' % (new_top, last_top))
    print('  新控件 id: bg=%d btn=%d val=%d' % (host['textview__wall_bg']['id'],
                                                host['button__wall']['id'],
                                                host['textview__wall_val']['id']))


if __name__ == '__main__':
    gen_wall_page()
    add_settings_entry()
