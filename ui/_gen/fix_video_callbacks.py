# -*- coding: utf-8 -*-
"""videoLogic.cc 回调段整体重写（去掉级联替换造成的重复定义）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'src', 'logic', 'videoLogic.cc')
t = open(p, encoding='utf-8').read()

marker = '// \u2500\u2500 \u56de\u8c03 \u2500'
idx = t.find(marker)
assert idx > 0, 'marker not found'
head = t[:idx]

block = []
block.append('// \u2500\u2500 \u56de\u8c03 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n')
block.append('static bool onButtonClick_ButtonVidBack(ZKButton *pButton) {\n')
block.append('    (void)pButton;\n')
block.append('    EASYUICONTEXT->goBack();\n')
block.append('    return true;\n')
block.append('}\n\n')
block.append('static void toggleRow(int i) {\n')
block.append('    if (i < 0 || i >= (int)sFiles.size()) return;\n')
block.append('    if (sSel.empty()) {                    // \u9996\u6b21\u70b9\u51fb\uff1a\u628a\u5168\u9009\u5c55\u5f00\u6210\u663e\u5f0f\u6e05\u5355\n')
block.append('        for (size_t k = 0; k < sFiles.size(); k++) sSel.push_back(sFiles[k]);\n')
block.append('    }\n')
block.append('    for (size_t k = 0; k < sSel.size(); k++) {\n')
block.append('        if (sSel[k] == sFiles[i]) {\n')
block.append('            sSel.erase(sSel.begin() + k);\n')
block.append('            saveConfig();\n')
block.append('            refreshRows();\n')
block.append('            return;\n')
block.append('        }\n')
block.append('    }\n')
block.append('    sSel.push_back(sFiles[i]);\n')
block.append('    saveConfig();\n')
block.append('    refreshRows();\n')
block.append('}\n\n')
for i in range(12):
    block.append('static bool onButtonClick_ButtonVidRow%d(ZKButton *p) { (void)p; toggleRow(%d); return true; }\n' % (i + 1, i))
block.append('\n')
block.append('static bool onButtonClick_ButtonVidIntN(int idx) {\n')
block.append('    if (idx < 0 || idx > 5) return true;\n')
block.append('    sInterval = kIntervalSec[idx];\n')
block.append('    StoragePreferences::putInt(KEY_VIDEO_INT, sInterval);\n')
block.append('    refreshInterval();\n')
block.append('    return true;\n')
block.append('}\n')
for i in range(6):
    block.append('static bool onButtonClick_ButtonVidInt%d(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(%d); }\n' % (i + 1, i))

open(p, 'w', encoding='utf-8').write(head + ''.join(block))
print('videoLogic.cc \u56de\u8c03\u6bb5\u5df2\u91cd\u5199')
