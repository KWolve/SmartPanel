# -*- coding: utf-8 -*-
"""编辑模式外边框改为**一个 .9.png 走天下**（钟工 2026-09-24 22:33：「实际你可以用一个 .9.png 就可以了」）。
生成 resources/images/edit_box.9.png：1px 9-patch marker 环（黑）+ 内侧 2px 强调绿边框 + 四角 L 角标。
再按 5 个控件的真实尺寸做**9-patch 拉伸模拟**，合成一张预览图。
同时删掉之前按尺寸生成的 5 张固定框（已被 .9 取代）。
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
ACC = (0x7B, 0xE0, 0xA3, 240)

# ---- ① 造 9-patch 源图：24x24；外圈 1px 为 marker；内容 22x22 ----
S = 24
im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
# 边框（画在 marker 环内侧）：2px
d.rectangle([1, 1, S - 2, S - 2], outline=ACC, width=2)
# 角标（内侧 L，不参与拉伸区）
L = 6
for (cx, cy, sx, sy) in ((1, 1, 1, 1), (S - 2, 1, -1, 1), (1, S - 2, 1, -1), (S - 2, S - 2, -1, -1)):
    d.rectangle([cx if sx > 0 else cx - L, cy, cx + L if sx > 0 else cx, cy + 1], fill=ACC)
    d.rectangle([cx, cy if sy > 0 else cy - L, cx + 1, cy + L if sy > 0 else cy], fill=ACC)
# marker 环：上/左 标记 stretch 区（中间段），下/右 标记 content 区（同样中间段）
BLACK = (0, 0, 0, 255)
for x in range(3, S - 3):
    im.putpixel((x, 0), BLACK)          # 上：stretch
    im.putpixel((x, S - 1), BLACK)      # 下：content
for y in range(3, S - 3):
    im.putpixel((0, y), BLACK)          # 左：stretch
    im.putpixel((S - 1, y), BLACK)      # 右：content
p9 = os.path.join(IMGS, 'edit_box.9.png')
im.save(p9)
print('written', p9, os.path.getsize(p9), 'B', im.size)


def nine_stretch(src, w, h, marker=1):
    """按 9-patch 规则把 src 拉到 w x h（marker = 外圈 marker 宽度）。"""
    inner = src.crop((marker, marker, src.width - marker, src.height - marker))
    xs, ys = inner.width, inner.height
    quad = 6                                     # 缩放区取角标大小
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    # 9 宫格：四角原样，四边拉伸，中间拉伸
    regions = [
        ((0, 0, quad, quad), (0, 0, quad, quad)),
        ((quad, 0, xs - quad, quad), (quad, 0, w - quad, quad)),
        ((xs - quad, 0, xs, quad), (w - quad, 0, w, quad)),
        ((0, quad, quad, ys - quad), (0, quad, quad, h - quad)),
        ((quad, quad, xs - quad, ys - quad), (quad, quad, w - quad, h - quad)),
        ((xs - quad, quad, xs, ys - quad), (w - quad, quad, w, h - quad)),
        ((0, ys - quad, quad, ys), (0, h - quad, quad, h)),
        ((quad, ys - quad, xs - quad, ys), (quad, h - quad, w - quad, h)),
        ((xs - quad, ys - quad, xs, ys), (w - quad, h - quad, w, h)),
    ]
    for src_box, dst_box in regions:
        piece = inner.crop(src_box)
        dw, dh = dst_box[2] - dst_box[0], dst_box[3] - dst_box[1]
        if dw <= 0 or dh <= 0:
            continue
        out.paste(piece.resize((dw, dh), Image.BOX), (dst_box[0], dst_box[1]))
    return out


# ---- ② 预览：按 5 个控件真实尺寸拉伸合成 ----
BOXES = [('时间', 480, 140, 0, 86), ('日期', 480, 28, 0, 236), ('天气', 168, 24, 188, 282),
         ('温湿度', 480, 28, 0, 326), ('状态条', 452, 40, 16, 396)]
prev = Image.new('RGBA', (480, 480), (0x17, 0x17, 0x1B, 255))
for label, w, h, left, top in BOXES:
    prev.alpha_composite(nine_stretch(im, w, h), (left, top))
out = os.path.join(ROOT, 'proto_render', 'edit_box_preview.png')
os.makedirs(os.path.dirname(out), exist_ok=True)
prev.convert('RGB').save(out)
print('预览 ->', out)

# ---- ③ 删掉已被 .9 取代的 5 张固定框 ----
for f in ('ss_ed_time.png', 'ss_ed_date.png', 'ss_ed_weather.png', 'ss_ed_th.png', 'ss_ed_bar.png'):
    p = os.path.join(IMGS, f)
    if os.path.exists(p):
        os.remove(p)
        print('removed', f)
