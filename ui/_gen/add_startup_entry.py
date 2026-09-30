# -*- coding: utf-8 -*-
"""加一个远程验收入口：启动页可由 setprop 指定（便于我自己逐页截图验收，不用触摸注入）。
   setprop sys.zkapp.startup settingsActivity ; setprop ctl.restart zkswe
   不设 = 默认 mainActivity（屏保）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'src', 'Main.cpp')
t = open(p, encoding='utf-8').read()

if 'zkapp.startup' in t:
    print('已有 startup 入口，跳过')
else:
    # include
    if '#include "os/SystemProperties.h"' not in t:
        if '#include "entry/EasyUIContext.h"' in t:
            t = t.replace('#include "entry/EasyUIContext.h"',
                          '#include "entry/EasyUIContext.h"\n#include "os/SystemProperties.h"', 1)
        else:
            t = t.replace('#include <cstdlib>', '#include <cstdlib>\n#include "os/SystemProperties.h"', 1)
    old = '''const char* onStartupApp(EasyUIContext *pContext) {
    return "mainActivity";
}'''
    new = '''const char* onStartupApp(EasyUIContext *pContext) {
    (void)pContext;
    // 远程验收入口：想直接看某一页时（不需触摸）——
    //   setprop sys.zkapp.startup settingsActivity ; setprop ctl.restart zkswe
    // 可选值：mainActivity(屏保) / homeActivity / settingsActivity / brightnessActivity /
    //         videoActivity / albumActivity / sssetActivity；不设=mainActivity。
    static std::string sStartup;
    std::string prop = SystemProperties::getString("sys.zkapp.startup", "mainActivity");
    sStartup = prop.empty() ? std::string("mainActivity") : prop;
    printf("onStartupApp -> %s\\n", sStartup.c_str());
    return sStartup.c_str();
}'''
    assert old in t, 'Main.cpp onStartupApp 未匹配'
    t = t.replace(old, new, 1)
    if '#include <string>' not in t:
        t = t.replace('#include "os/SystemProperties.h"', '#include "os/SystemProperties.h"\n#include <string>', 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('Main.cpp: 已加 sys.zkapp.startup 启动页入口')
