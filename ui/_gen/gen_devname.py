# -*- coding: utf-8 -*-
"""生成「设备名称」修改页（ui/devname.json）+ 修正相册页 Title 垂直对齐（问题单 09251751-6/7）
用法：python ui/_gen/gen_devname.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')

C_BG, C_IC, C_GN = 0x17171B, 0x31313A, 0x7BE0A3
C_TX, C_SUB, C_DIM = 0xECECF0, 0x9AA0A6, 0x5F5F68
AL_LT, AL_CC, AL_RC = 0, 5, 6


def max_ids():
    m = {'textview__': 0, 'button__': 0, 'edittext__': 0}
    for p in glob.glob(os.path.join(UI, '*.json')):
        data = json.load(open(p, encoding='utf-8'))

        def walk(o):
            for k, v in o.items():
                if isinstance(v, dict):
                    for pre in m:
                        if k.startswith(pre) and v.get('id', 0) > m[pre]:
                            m[pre] = v['id']
                    walk(v)
        walk(data)
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

    def tv(self, host, cap, l, t, w, h, size, color, align, text='', pic=None):
        c = {'id': self._id('textview'), 'caption': cap,
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

    def edit(self, host, cap, l, t, w, h, text=''):
        c = {'id': self._id('edittext'), 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': 4, 'fontSize': 20, 'text': text, 'touchable': True,
             'visible': True, 'textColor': C_TX,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1},
             'colorTab': {'color0': C_TX, 'color1': -1, 'color2': -1, 'color3': -1,
                          'color4': -1},
             'password': False, 'maxLength': 24, 'inputType': 0,
             'bold': False, 'hintTextColor': 0x5F5F68, 'hintText': '输入设备名称',
             'textType': 0}
        host[self._key('edittext')] = c
        return c


def main():
    g = Gen()
    r = {'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
         'resolution': {'height': 480, 'width': 480}, 'topmost': False,
         'position': {'height': 480, 'left': 0, 'top': 0, 'width': 480}}

    g.tv(r, 'TextDnTitle', 20, 12, 260, 30, 22, C_TX, AL_LT, '设备名称')
    g.tv(r, 'TextDnTitleEn', 20, 44, 300, 22, 18, C_DIM, AL_LT, 'DEVICE NAME')
    g.btn(r, 'ButtonDnBack', 372, 16, 90, 32, '返回 >', C_GN, 18, AL_RC)

    g.tv(r, 'ImageDnRowBg', 14, 84, 452, 46, 16, C_TX, AL_CC, '', 'images/srow452x46.png')
    g.tv(r, 'TextDnLabel', 30, 96, 90, 22, 18, C_SUB, AL_LT, '名称')
    g.edit(r, 'EditDnName', 118, 88, 330, 38)

    g.tv(r, 'TextDnHint1', 20, 148, 440, 22, 16, C_SUB, AL_LT,
         '名称会随 HA 上报（后台按设备名区分设备）')
    g.tv(r, 'TextDnHint2', 20, 174, 440, 22, 16, C_DIM, AL_LT,
         '最多 24 个字符；建议用房间名 - 位置')
    g.tv(r, 'TextDnCur', 20, 214, 440, 24, 18, C_TX, AL_LT, '当前：')

    g.btn(r, 'ButtonDnSave', 20, 412, 216, 48, '保存', C_TX, 18, AL_CC,
          'images/af_btn216x48.png')
    g.btn(r, 'ButtonDnCancel', 244, 412, 216, 48, '取消', C_TX, 18, AL_CC,
          'images/af_btn216x48.png')

    json.dump(r, open(os.path.join(UI, 'devname.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    n = sum(1 for k in r if '__' in k)
    print('devname.json: %d controls' % n)

    # ── 6) 相册页 Title 垂直对齐：top 8 -> 12（与 ssset/off/video 一致） ──
    p = os.path.join(UI, 'album.json')
    d = json.load(open(p, encoding='utf-8'))
    cnt = [0]

    def walk(o):
        for k, v in o.items():
            if isinstance(v, dict) and 'position' in v and v.get('caption') == 'TextAlTitle':
                v['position']['top'] = 12
                cnt[0] += 1
            if isinstance(v, dict):
                walk(v)
    walk(d)
    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('album.json: Title top -> 12 x%d' % cnt[0])


if __name__ == '__main__':
    main()
