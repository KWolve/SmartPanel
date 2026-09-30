# -*- coding: utf-8 -*-
"""重建「相册上传」页（album.json）为 v2 版（钟工 2026-09-25 12:29/12:33 定稿）：
  状态卡（相册图标 + 相册模式已开启 + 副行 + 呼吸灯/帧动画）
  + 二维码区（160x160 白卡 + qrcode 控件 + 「微信扫码传图」）
  + 上传类型数量行（图片/视频 + 绿徽标）
  + 混播说明 + 常规按钮「结束相册模式」
用法：python ui/_gen/rebuild_album_v2.py
"""
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
P = os.path.join(UI, 'album.json')

C_BG, C_SF, C_IC, C_GN = 0x17171B, 0x26262E, 0x31313A, 0x7BE0A3
C_TX, C_SUB, C_DIM, C_ON_TX = 0xECECF0, 0x9A9AA2, 0x5F5F68, 0x10141A
AL_LC, AL_CC, AL_RC, AL_LT = 1 | 4, 1 | 4, 2 | 4, 1


def max_ids():
    """(textview, button, qrcode) 全局最大 id"""
    m = {'textview__': 0, 'button__': 0, 'qrcode__': 0}
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
        self.out = None

    def _key(self, kind):
        self.seq[kind] = self.seq.get(kind, 0) + 1
        return '%s__%d' % (kind, self.seq[kind])

    def _id(self, kind):
        pre = kind + '__'
        self.mx[pre] = self.mx.get(pre, 0) + 1
        return self.mx[pre]

    def tv(self, host, cap, l, t, w, h, size, color, align, text='', pic=None,
           visible=True, bold=False):
        c = {'id': self._id('textview'), 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': align, 'colorTab': {'color0': color, 'color1': -1, 'color2': -1,
                                              'color3': -1, 'color4': -1},
             'fontSize': size, 'touchable': False, 'bold': bold, 'italic': False,
             'text': text, 'visible': visible, 'rollEnable': False, 'rollDirection': 1,
             'rollIntervalTime': 150, 'rollStep': 5,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1}}
        if pic:
            c['backgroundPic'] = pic
        host[self._key('textview')] = c
        return c

    def btn(self, host, cap, l, t, w, h, text='', color=C_TX, size=18, align=AL_CC,
            pic=None, visible=True):
        c = {'id': self._id('button'), 'caption': cap,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'alignment': align, 'colorTab': {'color0': color, 'color1': color, 'color2': -1,
                                              'color3': -1, 'color4': -1},
             'text': text, 'touchable': True, 'visible': visible, 'picTab': {},
             'longClickTimeOut': -1, 'longClickIntervalTime': -1,
             'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1,
                            'color4': -1}}
        if size:
            c['fontSize'] = size
        host[self._key('button')] = c
        return c

    def qrcode(self, host, cap, l, t, w, h, code):
        c = {'id': self._id('qrcode'), 'caption': cap, 'codeStr': code, 'padding': 10,
             'position': {'left': l, 'top': t, 'width': w, 'height': h},
             'backgroundColor': -1, 'touchable': True, 'visible': True}
        host[self._key('qrcode')] = c
        return c


def main():
    g = Gen()
    r = {'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
         'resolution': {'height': 480, 'width': 480}, 'topmost': False,
         'position': {'height': 480, 'left': 0, 'top': 0, 'width': 480}}

    # 标题区
    g.tv(r, 'TextAlTitle', 20, 8, 240, 30, 22, C_TX, AL_LT, '相册上传', bold=True)
    g.tv(r, 'TextAlTitleEn', 20, 40, 300, 22, 18, C_DIM, AL_LT, 'ALBUM UPLOAD')
    g.btn(r, 'ButtonAlBack', 372, 16, 90, 32, '返回 >', C_GN, 18, AL_RC)

    # 状态卡：图标 + 标题 + 副行 + 呼吸灯/帧动画
    g.tv(r, 'ImageAlModeBg', 14, 70, 452, 50, 16, C_TX, AL_CC, '', 'images/srow452x50.png')
    g.tv(r, 'ImageAlModeIconBg', 28, 78, 34, 34, 16, C_GN, AL_CC, '', 'images/sicon34x34.png')
    g.tv(r, 'ImageAlModeIcon', 35, 85, 20, 20, 16, C_GN, AL_CC, '', 'images/ic_image_g20.png')
    g.tv(r, 'TextAlModeTitle', 76, 76, 280, 24, 18, C_TX, AL_LT, '相册模式已开启', bold=True)
    g.tv(r, 'TextAlModeSub', 76, 100, 310, 22, 16, C_SUB, AL_LT, '等待手机 APP 上传 - 同一局域网自动发现')
    g.tv(r, 'ImageAlAnim', 398, 71, 48, 48, 16, C_TX, AL_CC, '', 'images/al_anim_0.png',
         visible=False)
    g.tv(r, 'ImageAlPulse', 416, 86, 16, 16, 16, C_GN, AL_CC, '', 'images/dot_pulse.png')

    # 二维码区（预留：微信扫码传图）
    g.tv(r, 'ImageAlQrCard', 160, 130, 160, 160, 16, C_TX, AL_CC, '', 'images/qr_card_160.png')
    g.qrcode(r, 'QrcodeAl', 176, 146, 128, 128, 'http://192.0.2.108:9000/upload')
    g.tv(r, 'TextAlQrCap', 140, 294, 200, 24, 18, C_TX, AL_CC, '微信扫码传图', bold=True)
    g.tv(r, 'TextAlQrHint', 100, 316, 280, 20, 16, C_SUB, AL_CC, '手机与面板需在同一 WiFi')

    # 上传类型数量
    g.tv(r, 'ImageAlCntBg', 14, 340, 452, 38, 16, C_TX, AL_CC, '', 'images/srow452x38.png')
    g.tv(r, 'TextAlImgLabel', 30, 348, 130, 22, 18, C_TX, AL_LT, '图片 JPG/PNG')
    g.tv(r, 'ImageAlImgBadge', 160, 347, 56, 24, 16, C_GN, AL_CC, '', 'images/cnt56x24.png')
    g.tv(r, 'TextAlImgCount', 160, 347, 56, 24, 16, C_ON_TX, AL_CC, '0 个')
    g.tv(r, 'TextAlVidLabel', 248, 348, 90, 22, 18, C_TX, AL_LT, '视频 MP4')
    g.tv(r, 'ImageAlVidBadge', 348, 347, 68, 24, 16, C_GN, AL_CC, '', 'images/cnt68x24.png')
    g.tv(r, 'TextAlVidCount', 348, 347, 68, 24, 16, C_ON_TX, AL_CC, '0 个')

    # 混播说明 + 结束按钮（常规样式）
    g.tv(r, 'TextAlMixHint', 20, 384, 440, 20, 16, C_DIM, AL_LT, '图片每张 15 秒（可配），与视频混播轮播')
    g.tv(r, 'ImageAlEndBg', 20, 412, 440, 48, 16, C_TX, AL_CC, '', 'images/btn_regular440x48.png')
    g.btn(r, 'ButtonAlEnd', 20, 412, 440, 48, '结束相册模式', C_TX, 18, AL_CC)

    with open(P, 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    n = sum(1 for k in r if '__' in k)
    print('album.json rebuilt: %d controls' % n)


if __name__ == '__main__':
    main()
