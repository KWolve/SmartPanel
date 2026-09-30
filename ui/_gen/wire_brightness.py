# -*- coding: utf-8 -*-
"""接线：设置页「屏幕亮度」行 → brightnessActivity；屏保页进入/退出时切换工作/屏保亮度。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGIC = os.path.join(ROOT, 'src', 'logic')


def patch(path, pairs, must=True):
    p = os.path.join(LOGIC, path)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        if old not in t:
            print('!! MISS %s: %r' % (path, old[:48]))
            if must:
                raise SystemExit(1)
            continue
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', path)


patch('settingsLogic.cc', [
    # 亮度行的装饰层放行
    ("        mButtonRowScenesBgPtr, mButtonRowScenesIconBgPtr, mButtonRowScenesIconPtr, mButtonRowScenesLabelPtr, mButtonRowScenesValuePtr, mButtonRowScenesChevronPtr,\n",
     "        mButtonRowScenesBgPtr, mButtonRowScenesIconBgPtr, mButtonRowScenesIconPtr, mButtonRowScenesLabelPtr, mButtonRowScenesValuePtr, mButtonRowScenesChevronPtr,\n"
     "        mButtonRowBrightBgPtr, mButtonRowBrightIconBgPtr, mButtonRowBrightIconPtr, mButtonRowBrightLabelPtr, mButtonRowBrightValuePtr, mButtonRowBrightChevronPtr,\n"),
    # 亮度行 → 亮度页
    ('static bool onButtonClick_ButtonRowOff(ZKButton *pButton) { (void)pButton; noteActivity(); LOGD("TODO openActivity(offActivity)"); return true; }',
     'static bool onButtonClick_ButtonRowBright(ZKButton *pButton) {\n'
     '    (void)pButton;\n'
     '    noteActivity();\n'
     '    EASYUICONTEXT->openActivity("brightnessActivity");\n'
     '    return true;\n'
     '}\n'
     'static bool onButtonClick_ButtonRowOff(ZKButton *pButton) { (void)pButton; noteActivity(); LOGD("TODO openActivity(offActivity)"); return true; }'),
])

patch('mainLogic.cc', [
    ('#include "os/SystemProperties.h"',
     '#include "os/SystemProperties.h"\n#include "utils/BrightnessHelper.h"\n#include "storage/ConfigStore.h"'),
    ('static void onUI_show() {\n    refreshSsClock();\n}',
     'static void onUI_show() {\n'
     '    refreshSsClock();\n'
     '    // 屏保亮度（进来切屏保亮度；退出时在 onUI_hide 恢复工作亮度）\n'
     '    BRIGHTNESSHELPER->setBrightness(ConfigStore::getInstance()->screensaverBrightness());\n'
     '}'),
    ('static void onUI_hide() {\n}',
     'static void onUI_hide() {\n'
     '    BRIGHTNESSHELPER->setBrightness(ConfigStore::getInstance()->workBrightness());\n'
     '}'),
])
