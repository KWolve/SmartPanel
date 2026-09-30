# -*- coding: utf-8 -*-
"""屏保视频子页收尾：①补 3 张固定尺寸图 ②settings 行接 videoActivity ③屏保页优先读 /data 选中清单。"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
SS = 4
SF = (0x26, 0x26, 0x2E, 255)
BD = (0x31, 0x31, 0x3A, 255)
GN = (0x7B, 0xE0, 0xA3, 255)


def rounded(w, h, radius, fill, border=None, bw=1):
    im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if border is not None:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=border)
        i = bw * SS
        d.rounded_rectangle([i, i, w * SS - 1 - i, h * SS - 1 - i],
                            radius=max(0, (radius - bw) * SS), fill=fill)
    else:
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=fill)
    return im.resize((w, h), Image.BOX)


for name, im in (('srow452x38.png', rounded(452, 38, 12, SF, BD)),
                 ('chip68x44.png', rounded(68, 44, 22, SF, BD)),
                 ('chip68x44_hl.png', rounded(68, 44, 22, GN))):
    p = os.path.join(IMGS, name)
    im.save(p)
    print('%-20s %s %d B' % (name, im.size, os.path.getsize(p)))

# ② settings 行 → videoActivity
p = os.path.join(ROOT, 'src', 'logic', 'settingsLogic.cc')
t = open(p, encoding='utf-8').read()
old = 'static bool onButtonClick_ButtonRowVideo(ZKButton *pButton) { (void)pButton; noteActivity(); LOGD("TODO openActivity(videoActivity)"); return true; }'
new = ('static bool onButtonClick_ButtonRowVideo(ZKButton *pButton) {\n'
       '    (void)pButton;\n'
       '    noteActivity();\n'
       '    EASYUICONTEXT->openActivity("videoActivity");\n'
       '    return true;\n'
       '}')
assert old in t, 'settingsLogic: ButtonRowVideo 未找到'
t = t.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(t)
print('settingsLogic: ButtonRowVideo -> videoActivity')

# ③ 屏保页优先读 /data 选中清单
p = os.path.join(ROOT, 'src', 'logic', 'mainLogic.cc')
t = open(p, encoding='utf-8').read()
t = t.replace('#include "storage/ConfigStore.h"',
              '#include "storage/ConfigStore.h"\n#include "storage/StoragePreferences.h"', 1)
old = '''static void loadVideoList() {
    sVideos.clear();'''
new = '''static void loadVideoList() {
    sVideos.clear();
    // 优先用 /data 里的选中清单（屏保视频子页配置；空 = 未配置 → 退扫目录）
    std::string all = StoragePreferences::getString("sp_video_sel", "");
    size_t pos = 0;
    while (pos < all.size()) {
        size_t nl = all.find('\\n', pos);
        std::string one = all.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        if (!one.empty()) sVideos.push_back(one);
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    if (!sVideos.empty()) {
        LOGD("screensaver videos(from /data sel): %d", (int)sVideos.size());
        return;
    }'''
assert old in t, 'mainLogic: loadVideoList 未找到'
t = t.replace(old, new, 1)
open(p, 'w', encoding='utf-8').write(t)
print('mainLogic: loadVideoList 优先 /data 选中清单')
