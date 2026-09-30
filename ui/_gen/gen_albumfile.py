# -*- coding: utf-8 -*-
"""生成「相册文件管理」页（ui/albumfile.json + 所需图片资源）
钟工 2026-09-25 需求：相册上传增加文件管理页 -> 3x3 缩略图、图片/视频区分、
可全选或勾选其中一部分删除（删除带二次确认；删除时同步从屏保选中清单移除）。
用法：python ui/_gen/gen_albumfile.py
"""
import glob
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
IMG = os.path.join(ROOT, 'resources', 'images')
WS = os.path.dirname(os.path.dirname(ROOT))          # workspace 根
sys.path.insert(0, os.path.join(WS, 'tools', 'ui_tools'))
import gen_res  # noqa: E402  （项目工具：覆盖率口径出图，过 corner_audit）

C_BG, C_SF, C_IC, C_GN = 0x17171B, 0x26262E, 0x31313A, 0x7BE0A3
C_TX, C_SUB, C_DIM, C_ON_TX = 0xECECF0, 0x9AA0A6, 0x5F5F68, 0x10141A
C_DG, C_DGT = 0x3A2226, 0xE08B8B
AL_LC, AL_CC, AL_RC, AL_LT = 1 | 4, 1 | 4, 2 | 4, 1
GRID_X, GRID_Y, CW, CH, GX, GY = 14, 114, 140, 88, 16, 8


def rgb(c, a=255):
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF, a)


# ── 资源 ────────────────────────────────────────────────────────────
def gen_assets():
    os.makedirs(IMG, exist_ok=True)
    gen_res.save(gen_res.bordered_cov(140, 88, 8, rgb(C_SF), rgb(C_IC)), IMG, 'af_thumb140x88.png')
    gen_res.save(gen_res.bordered_cov(140, 44, 10, rgb(C_SF), rgb(C_IC)), IMG, 'af_btn140x44.png')
    gen_res.save(gen_res.bordered_cov(150, 44, 10, rgb(C_SF), rgb(C_IC)), IMG, 'af_btn150x44.png')
    gen_res.save(gen_res.bordered_cov(150, 44, 10, rgb(C_DG), rgb(C_DGT)), IMG, 'af_btn_dg150x44.png')
    gen_res.save(gen_res.bordered_cov(140, 44, 10, rgb(C_IC), rgb(C_GN)), IMG, 'af_btn_hi140x44.png')
    gen_res.save(gen_res.bordered_cov(140, 44, 10, rgb(C_DG), rgb(C_DGT)), IMG, 'af_btn_dg140x44.png')
    gen_res.save(gen_res.bordered_cov(380, 184, 14, rgb(0x1E1E24), rgb(C_IC)), IMG, 'af_card380x184.png')

    ring = gen_res.ring_cov_alpha(148, 96, 10, 2)
    fr = Image.new('RGBA', (148, 96), rgb(C_GN))
    fr.putalpha(ring)
    gen_res.save(fr, IMG, 'af_selframe148x96.png')

    dim = Image.new('RGBA', (480, 480), (0, 0, 0, 150))
    gen_res.save(dim, IMG, 'af_dim480.png')


def check_icon(size, on):
    """勾选图标：SS 画 -> BOX 缩（AREA/BOX 口径，禁 LANCZOS/BICUBIC）"""
    ss = 4
    big = Image.new('RGBA', (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if on:
        d.ellipse([0, 0, size * ss - 1, size * ss - 1], fill=rgb(C_GN))
        w = max(1, size * ss // 9)
        d.line([size * ss * 0.26, size * ss * 0.54, size * ss * 0.44, size * ss * 0.72],
               fill=rgb(C_ON_TX), width=w)
        d.line([size * ss * 0.44, size * ss * 0.72, size * ss * 0.76, size * ss * 0.30],
               fill=rgb(C_ON_TX), width=w)
    else:
        d.ellipse([0, 0, size * ss - 1, size * ss - 1], fill=(0x10, 0x10, 0x14, 150))
        d.ellipse([0, 0, size * ss - 1, size * ss - 1], outline=(0xC8, 0xC8, 0xD0, 200),
                  width=max(1, ss // 2))
    return big.resize((size, size), Image.BOX)


def gen_icons():
    gen_res.save(check_icon(24, True), IMG, 'af_check_on24.png')
    gen_res.save(check_icon(24, False), IMG, 'af_check_off24.png')


# ── json ────────────────────────────────────────────────────────────
def max_ids():
    m = {'textview__': 0, 'button__': 0, 'qrcode__': 0, 'window__': 0}
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
        if pic:
            c['backgroundPic'] = pic
        if size:
            c['fontSize'] = size
        host[self._key('button')] = c
        return c


def main():
    gen_assets()
    gen_icons()
    g = Gen()
    r = {'backgroundColor': C_BG, 'beepEnable': True, 'id': 0,
         'resolution': {'height': 480, 'width': 480}, 'topmost': False,
         'position': {'height': 480, 'left': 0, 'top': 0, 'width': 480}}

    g.tv(r, 'TextAfTitle', 20, 8, 260, 30, 22, C_TX, AL_LT, '相册文件管理', bold=True)
    g.tv(r, 'TextAfTitleEn', 20, 40, 300, 22, 18, C_DIM, AL_LT, 'ALBUM FILES')
    g.btn(r, 'ButtonAfBack', 372, 16, 90, 32, '返回 >', C_GN, 18, AL_RC)

    # 统计行
    g.tv(r, 'ImageAfInfoBg', 14, 68, 452, 38, 16, C_TX, AL_CC, '', 'images/srow452x38.png')
    g.tv(r, 'TextAfStat', 30, 76, 300, 22, 18, C_TX, AL_LT, '共 0 个文件 - 已选 0 个')
    g.tv(r, 'TextAfPage', 306, 76, 144, 22, 16, C_SUB, AL_RC, '1/1')

    # 3x3 网格：每格 = 选中框 + 缩略图 + 类型徽标 + 勾选 + 点击按钮
    for i in range(9):
        cx = GRID_X + (i % 3) * (CW + GX)
        cy = GRID_Y + (i // 3) * (CH + GY)
        n = i + 1
        g.tv(r, 'ImageAfSelFrame%d' % n, cx - 4, cy - 4, 148, 96, 16, C_GN, AL_CC, '',
             'images/af_selframe148x96.png', visible=False)
        g.tv(r, 'ImageAfThumb%d' % n, cx, cy, CW, CH, 16, C_TX, AL_CC, '',
             'images/af_thumb140x88.png')
        g.tv(r, 'ImageAfKind%d' % n, cx + CW - 46, cy + 6, 40, 22, 16, C_GN, AL_CC, '',
             'images/badge_image.png', visible=False)
        # 视频格：居中胶片图标（钟工 2026-09-25 收尾）
        g.tv(r, 'ImageAfFilm%d' % n, cx + CW // 2 - 10, cy + CH // 2 - 10, 20, 20, 16, C_GN,
             AL_CC, '', 'images/ic_film_g20.png', visible=False)
        g.tv(r, 'ImageAfCheck%d' % n, cx + 6, cy + 6, 24, 24, 16, C_GN, AL_CC, '',
             'images/af_check_off24.png', visible=False)
        g.btn(r, 'ButtonAfCell%d' % n, cx, cy, CW, CH, '')

    g.tv(r, 'TextAfEmpty', 60, 240, 360, 24, 18, C_DIM, AL_CC,
         '暂无文件 - 用手机小程序上传', visible=False)

    # 底部操作条
    g.btn(r, 'ButtonAfAll', 14, 412, 140, 44, '全选', C_TX, 18, AL_CC,
          'images/af_btn140x44.png')
    g.btn(r, 'ButtonAfDel', 170, 412, 140, 44, '删除所选', C_TX, 18, AL_CC,
          'images/af_btn_dg140x44.png')
    g.btn(r, 'ButtonAfDone', 326, 412, 140, 44, '完成', C_TX, 18, AL_CC,
          'images/af_btn140x44.png')

    # 删除确认弹窗：不用 window（生成器不出窗口指针）——改为根节点下的一组普通控件，
    # 全部默认隐藏，靠 afDialog() 开关；另加一个全屏垫层按钮吃掉误触（点击不做事）。
    g.tv(r, 'ImageAfDim', 0, 0, 480, 480, 16, C_TX, AL_CC, '', 'images/af_dim480.png',
         visible=False)
    g.btn(r, 'ButtonAfDimHit', 0, 0, 480, 480, '', C_TX, 16, AL_CC, visible=False)
    g.tv(r, 'ImageAfDelCard', 50, 150, 380, 184, 16, C_TX, AL_CC, '',
         'images/af_card380x184.png', visible=False)
    g.tv(r, 'TextAfDelTitle', 78, 172, 324, 26, 20, C_TX, AL_LT, '删除所选文件？', bold=True,
         visible=False)
    g.tv(r, 'TextAfDelSub', 78, 204, 324, 22, 16, C_SUB, AL_LT, '共 0 个，删除后不可恢复',
         visible=False)
    g.btn(r, 'ButtonAfDelCancel', 78, 262, 150, 44, '取消', C_TX, 18, AL_CC,
          'images/af_btn150x44.png', visible=False)
    g.btn(r, 'ButtonAfDelOk', 252, 262, 150, 44, '删除', C_TX, 18, AL_CC,
          'images/af_btn_dg150x44.png', visible=False)

    with open(os.path.join(UI, 'albumfile.json'), 'w', encoding='utf-8') as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    n = sum(1 for k in r if '__' in k)
    print('albumfile.json: %d controls' % n)


if __name__ == '__main__':
    main()
