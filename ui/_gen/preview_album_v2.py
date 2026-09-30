# -*- coding: utf-8 -*-
"""相册上传页 v2 效果预览图（480x480，含二维码区域 / 呼吸灯 / 类型数量统计 / 结束相册模式按钮）。
   用真实设计令牌 + 项目里已有的素材合成，供钟工过目后再落 json/代码。
用法：python ui/_gen/preview_album_v2.py
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont
import segno

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMGS = os.path.join(ROOT, 'resources', 'images')
OUT = os.path.join(ROOT, 'proto_render', 'album_v2_preview.png')

BG = (0x17, 0x17, 0x1B)
SF = (0x26, 0x26, 0x2E)
IC = (0x31, 0x31, 0x3A)
GN = (0x7B, 0xE0, 0xA3)
TX = (0xEC, 0xEC, 0xF0)
SUB = (0x9A, 0x9A, 0xA2)
DIM = (0x5F, 0x5F, 0x68)
DANGER = (0xE0, 0x70, 0x70)
ON_GN = (0x10, 0x14, 0x1A)

W = H = 480
QR_PAYLOAD = 'https://zkswe.com/panel/upload?dev=PANEL-SAMPLE01'


def font(size, bold=False):
    p = r'C:\Windows\Fonts\msyhbd.ttc' if bold else r'C:\Windows\Fonts\msyh.ttc'
    return ImageFont.truetype(p, size)


def asset(name):
    return Image.open(os.path.join(IMGS, name)).convert('RGBA')


def paste(base, name, x, y):
    a = asset(name)
    base.alpha_composite(a, (x, y))
    return a.size


def main():
    im = Image.new('RGBA', (W, H), BG + (255,))
    d = ImageDraw.Draw(im)

    # ── 标题区 ──
    d.text((20, 8), '相册上传', font=font(22, True), fill=TX)
    d.text((20, 40), 'ALBUM UPLOAD', font=font(18), fill=SUB)
    bt = '返回 >'
    tw = d.textlength(bt, font=font(18))
    d.text((462 - tw, 16), bt, font=font(18), fill=GN)

    # ── 状态卡（大号相册图标 + 呼吸灯/帧动画 + 状态文字）──
    paste(im, 'srow452x50.png', 14, 70)
    # 图标底 + 绿色相册图标
    d.rounded_rectangle([28, 78, 62, 112], radius=10, fill=IC)
    paste(im, 'ic_image_g20.png', 35, 85)
    d.text((76, 76), '相册模式已开启', font=font(18, True), fill=TX)
    d.text((76, 100), '正在接收素材…（帧动画 8 帧循环）', font=font(16), fill=GN)
    # 帧动画一帧（接收态）
    paste(im, 'al_anim_2.png', 402, 74)

    # ── 二维码区（预留：微信扫码传图）──
    d.rounded_rectangle([160, 130, 320, 290], radius=16, fill=(0xFF, 0xFF, 0xFF))
    qr = segno.make(QR_PAYLOAD, error='m')
    buf = io.BytesIO()
    qr.save(buf, kind='png', scale=1, border=0, dark='#10141A', light=None)
    qimg = Image.open(buf).convert('RGBA')
    qimg = qimg.resize((128, 128), Image.NEAREST)
    im.alpha_composite(qimg, (176, 146))
    cap = '微信扫码传图'
    tw = d.textlength(cap, font=font(18, True))
    d.text((240 - tw / 2, 294), cap, font=font(18, True), fill=TX)
    hint = '手机与面板需在同一 WiFi'
    tw = d.textlength(hint, font=font(16))
    d.text((240 - tw / 2, 316), hint, font=font(16), fill=SUB)

    # ── 上传内容类型与数量 ──
    paste(im, 'srow452x38.png', 14, 340)
    d.text((30, 348), '图片 JPG/PNG', font=font(18), fill=TX)
    d.rounded_rectangle([160, 347, 216, 371], radius=12, fill=GN)
    t = '2 个'
    tw = d.textlength(t, font=font(16, True))
    d.text((188 - tw / 2, 352), t, font=font(16, True), fill=ON_GN)
    d.text((248, 348), '视频 MP4', font=font(18), fill=TX)
    d.rounded_rectangle([348, 347, 416, 371], radius=12, fill=GN)
    t = '10 个'
    tw = d.textlength(t, font=font(16, True))
    d.text((382 - tw / 2, 352), t, font=font(16, True), fill=ON_GN)

    # ── 混播说明 ──
    d.text((20, 384), '图片每张 15 秒（可配），与视频混播轮播', font=font(16), fill=DIM)

    # ── 结束相册模式（常规按钮：灰底 + 亮字，不用危险色）──
    d.rounded_rectangle([20, 412, 460, 460], radius=14, fill=IC, outline=(0x3E, 0x3E, 0x48), width=1)
    t = '结束相册模式'
    tw = d.textlength(t, font=font(18, True))
    d.text((240 - tw / 2, 424), t, font=font(18, True), fill=TX)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    im.convert('RGB').save(OUT)
    print('preview ->', OUT)
    print('qr payload =', QR_PAYLOAD)


if __name__ == '__main__':
    main()
