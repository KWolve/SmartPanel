# -*- coding: utf-8 -*-
"""拼音输入法落地（开发期）：拷贝 dict_pinyin.dat + 重建 prefs 里的两条 EasyUI.cfg。

工程 prefs 的 EasyUI.cfg 是「JSON + 冒号前加反斜杠」的历史转义写法（"key"\\:value）。
历史文件里已出现过手拼坏的键，所以这里**按模板整条重建**（key 集与模板一致），不再增量打补丁。
debug = fun launch（资源在 /tmp/ui）｜release = 固化（资源在 /res/ui）
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = r'C:\Users\zkswe\.openclaw\workspace\gitcom\AppGroup\KaiduZ9\resources\ime\dict_pinyin.dat'


def cfg(root_dir, touch, uart, dict_path):
    return {
        'baud': '115200',
        'defBrightness': -1,
        'dictPinyinPath': dict_path,
        'languageCode': 'zh_CN',
        'languagePath': root_dir + '/tr/',
        'resPath': root_dir + '/ui/',
        'rotateScreen': 0,
        'rotateTouch': 0,
        'screensaverTimeOut': -1,
        'startupLibPath': root_dir + '/lib/libzkgui.so',
        'startupTouchCalib': False,
        'touchDev': touch,
        'uart': uart,
        'zkdebug': False,
    }


def dump(c):
    # 复刻工程转义写法：JSON 的 `":` 写成 `"\:`
    return json.dumps(c, ensure_ascii=False).replace('":', '"\\:')


def main():
    dst = os.path.join(ROOT, 'resources', 'ime', 'dict_pinyin.dat')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(SRC, dst)
    print('dict ->', dst, os.path.getsize(dst), 'B')

    lines = {
        'easyui.cfg.debug': cfg('/mnt/extsd', '/dev/input/event1', 'ttyS1',
                                '/tmp/ui/ime/dict_pinyin.dat'),
        'easyui.cfg.release': cfg('/res', '/dev/input/event1', 'ttyS1',
                                  '/res/ui/ime/dict_pinyin.dat'),
    }
    prefs = os.path.join(ROOT, '.settings', 'com.zksw.flythings.easyui.prefs')
    out = []
    for line in open(prefs, encoding='utf-8').read().split('\n'):
        key = line.split('=', 1)[0]
        if key in lines:
            line = key + '=' + dump(lines[key])
            back = json.loads(line.split('=', 1)[1].replace('\\:', ':'))
            print(key, '| keys', len(back), '| dictPinyinPath', back['dictPinyinPath'])
        out.append(line)
    open(prefs, 'w', encoding='utf-8').write('\n'.join(out))


if __name__ == '__main__':
    main()
