# -*- coding: utf-8 -*-
"""字库缺字自检：拿素材名/界面词做样本，报出每个 ttf 缺哪些字。"""
import glob
import os

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE = ('嫦娥4个小猫敲门蜘蛛侠金鱼白色双鱼流水生财兔子狗口袋'
          '屏保视频相册上传轮播间隔运行模式情景模式关屏设置亮度返回设备名称系统版本'
          '设置主页面板家庭联动WiFi天气温湿度日期时间开关客厅卧室厨房阳台灯窗帘插座')

for p in sorted(glob.glob(os.path.join(ROOT, 'font', '*.ttf'))):
    try:
        f = TTFont(p, fontNumber=0)
        cmap = f.getBestCmap()
        miss = ''.join(sorted({c for c in SAMPLE if ord(c) not in cmap}))
        print('%-26s %9d B  chars=%-6d missing(%d)= %s'
              % (os.path.basename(p), os.path.getsize(p), len(cmap), len(miss), miss or '-'))
    except Exception as e:
        print('%-26s ERR %s' % (os.path.basename(p), e))

print('\n--- ui/_gen/build_fonts.py 关键行 ---')
t = open(os.path.join(ROOT, 'ui', '_gen', 'build_fonts.py'), encoding='utf-8').read()
for i, line in enumerate(t.splitlines(), 1):
    if any(k in line for k in ('GB2312', 'gb2312', 'charset', 'level', 'SUBSET', 'range',
                               'unicodes', 'text=', 'TEXT', 'HANS', 'SRC', 'OUT', 'size')):
        print('%4d: %s' % (i, line.strip()[:120]))
