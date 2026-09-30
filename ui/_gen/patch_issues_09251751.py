# -*- coding: utf-8 -*-
"""问题单 09251751 批处理 1（墨羽）：
1) 子页全部关闭系统屏保：每页 onUI_show() 首行插入 EASYUICONTEXT->setScreensaverEnable(false);
   （钟工口径：只有主页 home 进入屏保；设置等子页不进屏保）
   homeLogic 的 onUI_show 改为开启 + 复位（主页仍是唯一进屏保的页）
2) 去掉 Main.cpp 的「按属性调试起页」（sys.zkapp.startup），固定 mainActivity
用法：python ui/_gen/patch_issues_09251751.py
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'src')

SUB_PAGES = ['settingsLogic.cc', 'videoLogic.cc', 'sssetLogic.cc', 'offLogic.cc',
             'modeLogic.cc', 'scenesLogic.cc', 'albumLogic.cc', 'albumfileLogic.cc',
             'brightnessLogic.cc']

LINE = '    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）\n'
HOMELINE = ('    EASYUICONTEXT->setScreensaverEnable(true);    // 只有主页进屏保（钟工 09251751-1）\n'
            '    EASYUICONTEXT->resetScreensaverTimeOut();\n')


def patch_subpage(fn):
    p = os.path.join(SRC, 'logic', fn)
    t = io.open(p, encoding='utf-8').read()
    if 'setScreensaverEnable(false)' in t:
        print('  %-24s 已有，跳过' % fn)
        return
    m = re.search(r'static void onUI_show\(\) \{\n', t)
    if not m:
        print('  %-24s !! 没有 onUI_show，需手工处理' % fn)
        return
    t = t[:m.end()] + LINE + t[m.end():]
    io.open(p, 'w', encoding='utf-8').write(t)
    print('  %-24s 插入 ok' % fn)


def patch_home():
    p = os.path.join(SRC, 'logic', 'homeLogic.cc')
    t = io.open(p, encoding='utf-8').read()
    m = re.search(r'static void onUI_show\(\) \{\n', t)
    if not m:
        print('  homeLogic.cc !! 没有 onUI_show')
        return
    if 'setScreensaverEnable(true)' in t:
        print('  homeLogic.cc 已有，跳过')
        return
    t = t[:m.end()] + HOMELINE + t[m.end():]
    io.open(p, 'w', encoding='utf-8').write(t)
    print('  homeLogic.cc 插入 ok')


def patch_main_cpp():
    p = os.path.join(SRC, 'Main.cpp')
    t = io.open(p, encoding='utf-8').read()
    if 'sys.zkapp.startup' not in t:
        print('  Main.cpp 已无 startup 属性，跳过')
        return
    # 把属性读取替换为固定主页
    t2 = re.sub(r'[^\n]*SystemProperties::getString\("sys\.zkapp\.startup"[^\n]*\n',
                '', t)
    # 找到使用该变量的地方（若形如 startupActivity）
    t2 = re.sub(r'[^\n]*sys\.zkapp\.startup[^\n]*\n', '', t2)
    io.open(p, 'w', encoding='utf-8').write(t2)
    print('  Main.cpp 去掉 startup 属性读取（需人工核对起页参数）')


if __name__ == '__main__':
    print('=== 1) 子页关闭系统屏保 ===')
    for f in SUB_PAGES:
        patch_subpage(f)
    print('=== 2) 主页开启 ===')
    patch_home()
    print('=== 3) Main.cpp 去调试起页 ===')
    patch_main_cpp()
