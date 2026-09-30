# -*- coding: utf-8 -*-
"""SmartPanel_HA 工程字体子集：常用字 + 标点 + 设计需要的符号。
- HanSans-Medium.ttf  = 默认全局字体（正文/标题）
- HanSansLight.ttf    = 屏保大时钟专用（数字 + 冒号，体积极小）
多字体排序铁律：文件名 ASCII 升序，最靠前 = 全局默认 → HanSans-Medium('HanSans-') < HanSansLight('HanSansL')
"""
import os
from fontTools import subset

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, 'font')

SRC_MEDIUM = r'C:\Users\zkswe\.openclaw\workspace\projects\tag\doc\HarmonyOS_Sans_SC_Medium.ttf'
SRC_LIGHT = r'C:\Users\zkswe\.openclaw\workspace\temp\sp_ha_font\res_ui_fzcircle.ttf'  # HarmonyOS Sans SC Light


def gb2312_level2():
    # GB2312 二级汉字（0xD8-0xF7）：嫦 娥 等一级没有的字都在这里
    out = []
    for hi in range(0xD8, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('gb2312'))
            except Exception:
                pass
    return out


def gb2312_level1():
    out = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('gb2312'))
            except Exception:
                pass
    return out


def charset_main():
    cs = gb2312_level1() + gb2312_level2()   # 全字库：一级+二级（含 嫦、娥 等）
    cs += [chr(c) for c in range(0x20, 0x7F)]                      # ASCII
    cs += list('，。、；：？！“”‘’（）《》【】「」…—–·~～%‰°℃±×÷'
               '≈≤≥→←↑↓√★●○□■△▲')
    extra = 0
    seen, s = set(), ''
    for c in cs:
        if c not in seen:
            seen.add(c)
            s += c
        else:
            extra += 1
    return s


def build(src, out, text, label):
    options = subset.Options(layout_features='*', notdef_outline=True,
                             recalc_bounds=True, glyph_names=True)
    font = subset.load_font(src, options)
    ss = subset.Subsetter(options=options)
    ss.populate(text=text)
    ss.subset(font)
    subset.save_font(font, out, options)
    font.close()
    print('%-18s %8d B  -> %s' % (label, os.path.getsize(out), out))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cs = charset_main()
    print('main charset: %d chars' % len(cs))
    build(SRC_MEDIUM, os.path.join(OUT_DIR, 'HanSans-Medium.ttf'), cs, 'HanSans-Medium')
    build(SRC_LIGHT, os.path.join(OUT_DIR, 'HanSansLight.ttf'), '0123456789:', 'HanSansLight')


if __name__ == '__main__':
    main()
