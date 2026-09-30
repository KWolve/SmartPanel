# -*- coding: utf-8 -*-
"""在「相册上传」页底部加「文件管理」入口（与「结束相册模式」并排）
用法：python ui/_gen/add_album_files_btn.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI = os.path.join(ROOT, 'ui')
IMG = os.path.join(ROOT, 'resources', 'images')
WS = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, os.path.join(WS, 'tools', 'ui_tools'))
import gen_res  # noqa: E402

C_SF, C_IC = 0x26262E, 0x31313A


def rgb(c, a=255):
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF, a)


# ── 倒角口径（2026-09-27 统一，与 fix_corners.py::rounded 同式）────────────
# SS=4 覆盖 + Image.BOX 面积平均，r=12，**无描边**（族内多数口径：srow452x50/38 等同款）
from PIL import Image as _PILImage, ImageDraw as _PILImageDraw
_SS = 4


def _rounded_cov(w, h, radius, fill):
    im = _PILImage.new('RGBA', (w * _SS, h * _SS), (0, 0, 0, 0))
    _PILImageDraw.Draw(im).rounded_rectangle(
        [0, 0, w * _SS - 1, h * _SS - 1], radius=radius * _SS, fill=fill)
    return im.resize((w, h), _PILImage.BOX)


def main():
    gen_res.save(_rounded_cov(216, 48, 12, rgb(C_SF)), IMG,
                 'af_btn216x48.png')

    p = os.path.join(UI, 'album.json')
    r = json.load(open(p, encoding='utf-8'))

    # 1) 结束按钮：440 -> 216，右移
    end = None
    for k, v in list(r.items()):
        if isinstance(v, dict) and v.get('caption') == 'ButtonAlEnd':
            end = v
            end['position'] = {'left': 244, 'top': 412, 'width': 216, 'height': 48}
    if end is None:
        raise SystemExit('未找到 ButtonAlEnd')
    for k, v in list(r.items()):
        if isinstance(v, dict) and v.get('caption') == 'ImageAlEndBg':
            v['position'] = {'left': 244, 'top': 412, 'width': 216, 'height': 48}
            v['backgroundPic'] = 'images/af_btn216x48.png'

    # 2) 新增：文件管理（垫层 + 按钮），放在结束按钮之前 -> 视觉/层级都在左侧
    mx_tv = mx_btn = 0
    for k, v in r.items():
        if isinstance(v, dict):
            if k.startswith('textview__'):
                mx_tv = max(mx_tv, v.get('id', 0))
            if k.startswith('button__'):
                mx_btn = max(mx_btn, v.get('id', 0))

    bg = {'id': mx_tv + 1, 'caption': 'ImageAlFilesBg',
          'position': {'left': 20, 'top': 412, 'width': 216, 'height': 48},
          'alignment': 1 | 4, 'colorTab': {'color0': -1, 'color1': -1, 'color2': -1,
                                           'color3': -1, 'color4': -1},
          'fontSize': 16, 'touchable': False, 'bold': False, 'italic': False, 'text': '',
          'visible': True, 'rollEnable': False, 'rollDirection': 1, 'rollIntervalTime': 150,
          'rollStep': 5, 'backgroundPic': 'images/af_btn216x48.png',
          'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}
    btn = {'id': mx_btn + 1, 'caption': 'ButtonAlFiles',
           'position': {'left': 20, 'top': 412, 'width': 216, 'height': 48},
           'alignment': 1 | 4, 'colorTab': {'color0': 0xECECF0, 'color1': 0xECECF0,
                                            'color2': -1, 'color3': -1, 'color4': -1},
           'text': '文件管理', 'touchable': True, 'visible': True, 'picTab': {},
           'longClickTimeOut': -1, 'longClickIntervalTime': -1, 'fontSize': 18,
           'bgColorTab': {'color0': -1, 'color1': -1, 'color2': -1, 'color3': -1, 'color4': -1}}

    # 重建该页所有 key（按控件的 key 顺序重排 textview__N/button__N，避免跳号）
    out = {}
    tv_i = btn_i = 0
    for k, v in r.items():
        if k == 'resolution' or k == 'position':
            out[k] = v
            continue
        if not isinstance(v, dict):
            out[k] = v
            continue
        if k.startswith('textview__'):
            if k == 'textview__1':
                out['textview__%d' % (tv_i + 1)] = bg
                tv_i += 1
            tv_i += 1
            out['textview__%d' % tv_i] = v
        elif k.startswith('button__'):
            if k == 'button__1':
                out['button__%d' % (btn_i + 1)] = btn
                btn_i += 1
            btn_i += 1
            out['button__%d' % btn_i] = v
        else:
            out[k] = v

    # 根节点字段顺序（resolution/position 之外的元数据放回）
    for k in list(r.keys()):
        if k not in out and not isinstance(r[k], dict):
            out[k] = r[k]

    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('album.json: 新增「文件管理」入口 + 结束按钮改为 216 宽')


if __name__ == '__main__':
    main()
