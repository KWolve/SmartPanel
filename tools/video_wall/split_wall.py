#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多屏拼接切块工具（PC 端，配套 ffmpeg/ffprobe）

用途：把一条"整墙"视频按时**横向等分**成 N 段（每段 = 单台面板的分辨率 480x480），
让 N 台面板各播自己那段，拼起来就是完整画面。

2026-09-27 口径③（钟工，本版）：**绿框 = 唯一裁剪窗口**
  · **没有"缝"（bezel）这个概念了**：数学里恒为 0，UI 不暴露，不画橙色斜纹，没有"丢弃区"。
  · N 个 480×480 绿框**相邻无缝**，其并集就是裁剪窗口；**框组以外的画面直接丢弃**。
  · 用户操作只有两件：**拖框组**（改裁剪原点）+ **缩放**（改框组相对视频的大小）；
    视频画面固定不动，框组始终被钳制在视频内 → 永远不会出现黑边。
  · 导出 = 框内所见：`crop(源矩形) → scale(N×480 × 480) → crop(480:480:i*480:0)`，
    **链里不得出现 pad**；不存在的画面不会被合成出来。
  · 唯一事实源：裁剪矩形 `crop=[x,y,w,h]`（源像素坐标，且恒有 w = N×h）。
    前后端用**同一个** `align_crop()` 做偶数对齐/钳制 → 画框与发请求都用它 → 所见即所出。

为什么必须"编码参数完全一样 + 每段首帧是 IDR"：
  · 各面板独立解码 → 只有段与段时间轴严格一致（帧数/fps/时长/关键帧位置相同），
    上层做"同一时刻同一帧"的相位对齐才成立；
  · 每段以 IDR 开头 → 起播/seek 到段内任意点都能立刻出画，不会花时间等关键帧。

切法（默认，推荐）：
  crop 等分 + **每段用完全相同的一套 x264 参数分别编码**（deterministic：
  同源帧 + 同参数 → 帧数与时间戳完全一致），并强制每 K 秒一个关键帧。
  也支持 --copy-split 模式：先整帧编码一次（含强制关键帧），再 -c copy 切（零重编，
  但只有"横向切片"能这么做时才有意义 —— 本工具的 crop 切必须重编，故默认重编）。

用法：
  # 1) 生成一条测试用整墙视频（960x480，带帧号 + 分屏标号）
  python split_wall.py sample --out sample_960x480.mp4 --cols 2 --seconds 20

  # 2) 切成 2 段
  python split_wall.py split --in sample_960x480.mp4 --cols 2 --out-dir out/wall2

  # 3) 校验（参数是否完全一致 / 首帧是否 IDR / 帧数与时长是否相同）
  python split_wall.py verify --dir out/wall2

⚠ 2.0（2026-09-27 16:xx）：**一个组 = 多个视频轮播**（playlist.json v2）
  · 组目录里每个 clip 一个子目录：c1/seg_1..N.mp4、c2/seg_1..N.mp4 …
  · playlist.json（v2，必须写）+ wall.json（v1 兼容壳，保留写）
  · **各 clip 可以长短不同**（这就是"播放时长没有约束"）；同一 clip 内 N 段必须等长、参数完全一致
  · 旧布局（组目录直接放 seg_<idx>.mp4，无 playlist.json）**继续支持**
  # 4) 多视频成组（每个源各自摆框，默认各自最大框居中）
  python split_wall.py group --in a.mp4 --in b.mp4 --cols 2 --group-name zksw-wall --out-dir out/g1
  python split_wall.py group --src a.mp4 b.mp4 c.mp4 --cols 3 --crop 1=128:64:1024:512 --crop 3=0:0:960:480
  python split_wall.py group --in a.mp4 --cols 2 --crop 0:0:960:480      # 不带 k= 的 crop 作用到所有 clip
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

PANEL_W, PANEL_H = 480, 480          # Z20 面板单屏分辨率


class _SrcList(argparse.Action):
    """让 `--in a.mp4 --in b.mp4` 与 `--src a.mp4 b.mp4` 共用同一个列表（按命令行出现顺序累加）"""

    def __call__(self, parser, ns, values, option_string=None):
        cur = list(getattr(ns, self.dest, None) or [])
        cur += (list(values) if isinstance(values, (list, tuple)) else [values])
        setattr(ns, self.dest, cur)

# ── 统一的编码参数（Z20/SSD202 解码友好：H.264、yuv420p、无 B 帧、固定 GOP、faststart）──
ENC = {
    'vcodec': 'libx264',
    'profile': 'main',      # 兼容性优先（baseline/main/high 都可用；高配可选 high）
    'level': '4.0',
    'pix_fmt': 'yuv420p',
    'fps': 25,
    'gop_sec': 1,           # 每 1 秒一个关键帧（段内 seek 更准）
    'bf': 0,                # 无 B 帧：解码顺序=显示顺序，seek 更准、延迟更低
    'crf': 20,              # 恒定质量；也可用 --bitrate 走码率优先
    'preset': 'medium',
    'movflags': '+faststart',
}


def run(cmd, check=True):
    p = subprocess.run(cmd, capture_output=True)
    if check and p.returncode != 0:
        sys.stderr.write('命令失败: %s\n%s\n' % (' '.join(cmd), p.stderr.decode('utf-8', 'replace')[-2000:]))
        raise SystemExit(1)
    return p


def ffprobe_json(path):
    p = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams',
             '-show_format', path])
    return json.loads(p.stdout.decode('utf-8', 'replace'))


def stream_info(path):
    j = ffprobe_json(path)
    v = None
    a = None
    for s in j.get('streams', []):
        if s.get('codec_type') == 'video' and v is None:
            v = s
        if s.get('codec_type') == 'audio' and a is None:
            a = s
    dur = float(j.get('format', {}).get('duration', 0) or 0)
    fps = 0.0
    if v and v.get('avg_frame_rate') and v['avg_frame_rate'] != '0/0':
        n, d = v['avg_frame_rate'].split('/')
        fps = float(n) / float(d) if float(d) else 0.0
    nb = int(v.get('nb_frames', 0) or 0) if v else 0
    kf = None
    if v:
        kf = int(v.get('nb_frames', 0) or 0) if False else None
    return {
        'file': os.path.basename(path),
        'width': int(v['width']) if v else 0,
        'height': int(v['height']) if v else 0,
        'vcodec': v.get('codec_name') if v else None,
        'profile': v.get('profile') if v else None,
        'level': v.get('level') if v else None,
        'pix_fmt': v.get('pix_fmt') if v else None,
        'fps': round(fps, 4),
        'nb_frames': nb,
        'duration': round(dur, 4),
        'has_audio': a is not None,
        'audio': (a.get('codec_name') if a else None),
    }


def first_keyframe_pts(path):
    """返回第一个关键帧的 pts_time（用于校验"首帧是否为 IDR"）"""
    p = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
             '-show_entries', 'frame=key_frame,pts_time', '-of', 'csv=p=0', path])
    for line in p.stdout.decode('utf-8', 'replace').splitlines():
        parts = [x.strip() for x in line.split(',') if x.strip() != '']
        if len(parts) >= 2:
            return (parts[0] == '1', float(parts[1]))
    return (False, 0.0)


def keyframe_times(path, limit=8):
    p = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
             '-show_entries', 'frame=key_frame,pts_time', '-of', 'csv=p=0', path])
    out = []
    for line in p.stdout.decode('utf-8', 'replace').splitlines():
        parts = [x.strip() for x in line.split(',') if x.strip() != '']
        if len(parts) >= 2 and parts[0] == '1':
            out.append(round(float(parts[1]), 3))
            if len(out) >= limit:
                break
    return out


# ── 裁剪几何（2026-09-27 口径③：绿框=唯一裁剪窗口；无缝、无 pad、无黑边）────────
# 唯一事实源 = 裁剪矩形 crop=[x,y,w,h]（源像素），恒满足 w = N×h。
# 前端（index.html 的 alignCrop/maxCrop）与后端**同一套规则**，所以"画出来的框"
# 和"发出去的 crop"逐像素相同 → 所见即所出。
def canvas_size(cols):
    """整墙画布尺寸：宽 = N×480，高 = 480（相邻格零间隙 —— **没有"缝"**）"""
    return max(1, int(cols)) * PANEL_W, PANEL_H


def _eveni(v):
    """取整并对齐偶数（yuv420p 的 crop/scale 要求偶数；负数向更小方向对齐）"""
    v = int(round(v))
    return v - (((v % 2) + 2) % 2)


def align_crop(crop, src_w, src_h):
    """把裁剪矩形对齐到偶数并**钳制在源内**（唯一事实源的正规化）。

    返回 [x,y,w,h]：都偶数，且 0<=x、0<=y、x+w<=src_w、y+h<=src_h
    （因为框组永远在视频里 → 结构上不可能有黑边）。
    """
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    x, y, w, h = [int(round(float(v))) for v in crop]
    w = min(max(2, _eveni(w)), max(2, _eveni(sw)))
    h = min(max(2, _eveni(h)), max(2, _eveni(sh)))
    x, y = _eveni(x), _eveni(y)
    if x + w > sw:
        x = _eveni(sw - w)
    if y + h > sh:
        y = _eveni(sh - h)
    if x < 0:
        x = 0
    if y < 0:
        y = 0
    if x + w > sw:
        w = max(2, _eveni(sw - x))
    if y + h > sh:
        h = max(2, _eveni(sh - y))
    return [x, y, w, h]


def max_crop(cols, src_w, src_h):
    """框组能取到的**最大**矩形（"铺满"档）：高 = min(源高, 源宽/N)，宽 = N×高。

    框组始终 ≤ 视频 → 永远不会有黑边；这是导入视频后的默认位置。
    """
    n = max(1, int(cols))
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    h = min(_eveni(sh), _eveni(sw / float(n)))
    h = max(2, h)
    w = n * h
    return align_crop([_eveni((sw - w) / 2.0), _eveni((sh - h) / 2.0), w, h], sw, sh)


def crop_from_zoom(cols, src_w, src_h, zoom, pos=None):
    """由「缩放」反推裁剪矩形。

    zoom = 输出像素/源像素（= 画布宽/crop.w）：zoom>1 放大（框更小），zoom<1 缩小（框更大）。
    pos = 框组中心在源上的坐标（不给=居中）。
    """
    n = max(1, int(cols))
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    cw, _ = canvas_size(n)
    z = float(zoom)
    if not (z > 0):
        return max_crop(n, sw, sh)
    hm = min(_eveni(sh), _eveni(sw / float(n)))          # 框组能取的最大高
    h = min(max(2, _eveni((cw / z) / n)), max(2, hm))
    w = n * h
    if pos:
        x, y = _eveni(float(pos[0]) - w / 2.0), _eveni(float(pos[1]) - h / 2.0)
    else:
        x, y = _eveni((sw - w) / 2.0), _eveni((sh - h) / 2.0)
    return align_crop([x, y, w, h], sw, sh)


# ── 每屏独立窗口（2026-09-28 口径④）：每个屏 = 一个自己的方框 ─────────────
# 网页版需求："每一个屏幕的窗口可以独立移动"，相邻两屏之间可以留出**缝**
# （物理拼缝：缝宽内的源画面不输出 = 丢弃）；缝 = 0 且连着摆时与旧口径逐像素等价。
# 规则：N 个方框边长必须一致（同一缩放），x/y 各自独立；导出时每屏单独
#       crop(s:s:x_i:y_i) → scale(480:480)，各段仍 480×480 / 参数一致。
def normalize_frame(frame, src_w, src_h, side=None):
    """把单个屏窗口规范化：[x,y,w,h] → [x,y,s,s]（偶数、方形、钳制在源内）"""
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    x, y, w, h = [float(v) for v in frame]
    s = int(side) if side else min(int(round(w)), int(round(h)))
    s = max(2, min(_eveni(s), _eveni(sw), _eveni(sh)))
    x, y = _eveni(x), _eveni(y)
    x = min(max(0, x), max(0, _eveni(sw - s)))
    y = min(max(0, y), max(0, _eveni(sh - s)))
    return [x, y, s, s]


def resolve_frames(cols, src_w, src_h, frames):
    """按"每屏一个独立窗口"解析几何（相邻两屏之间可留缝）。

    frames: [[x,y,w,h] × N]（源像素，每屏一个；须为正方形且各屏边长一致）
    · 边长不一致 → 各屏缩放不同（画面会对不上）→ 直接报错
    · regular=True（同 y、相邻无缝）时与旧单框口径等价（可用旧滤镜链）
    """
    n = max(1, int(cols))
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    canvas_w, canvas_h = canvas_size(n)
    req = [[float(v) for v in f] for f in (frames or [])]
    if len(req) != n:
        raise ValueError('每屏窗口数量应为 %d 个（收到 %d 个）' % (n, len(req)))
    for i, f in enumerate(req):
        if len(f) != 4:
            raise ValueError('第 %d 个屏窗口需要 [x,y,w,h]（收到 %r）' % (i + 1, f))
    sizes = [max(2, min(int(round(f[2])), int(round(f[3])))) for f in req]
    if max(sizes) - min(sizes) > 2:
        raise ValueError('各屏窗口大小必须一致（否则每屏缩放不同、拼起来对不上）：%s' % sizes)
    side = _eveni(min(sizes))
    fr = [normalize_frame(f, sw, sh, side) for f in req]
    gaps = [max(0, fr[i + 1][0] - (fr[i][0] + side)) for i in range(n - 1)]
    regular = bool(len({f[1] for f in fr}) == 1 and not any(gaps))
    x0 = min(f[0] for f in fr)
    y0 = min(f[1] for f in fr)
    x1 = max(f[0] for f in fr) + side
    y1 = max(f[1] for f in fr) + side
    crop = [x0, y0, n * side, side] if regular else [x0, y0, x1 - x0, y1 - y0]
    too_small = (sw < PANEL_W or sh < PANEL_H)
    return {'cols': n, 'canvas_w': canvas_w, 'canvas_h': canvas_h,
            'src_w': sw, 'src_h': sh, 'crop': crop, 'crop_requested': None,
            'crop_aligned': False, 'mode': 'frames',
            'frames': [list(f) for f in fr], 'regular': regular,
            'gaps': gaps, 'gap_px': int(max(gaps) if gaps else 0),
            'seam_w': int(max(gaps) if gaps else 0),
            'scale': round(canvas_w / float(n * side), 6),
            'src_px_per_out_px': round(side / float(PANEL_W), 6),
            'src_px_per_seg_px': round(side / float(PANEL_W), 6),
            'inside': True, 'aspect_ok': True, 'too_small': too_small,
            'valid': not too_small, 'seg_w': PANEL_W, 'seg_h': PANEL_H,
            'layout': '1x%d' % n}


def resolve_geometry(cols, src_w, src_h, crop=None, zoom=0.0, pos=None, fit='crop',
                     frames=None):
    """把输入解析成唯一事实源 geo。

    crop=[x,y,w,h] ：**原样使用**（只做偶数对齐 + 钳制），优先于 zoom/pos。
    frames=[N×[x,y,w,h]]：每屏一个独立方框（可留缝）→ 见 resolve_frames（优先于 crop）。
    zoom>0         ：crop = 画布宽/zoom 宽、高 = 宽/N（pos=中心，缺省居中）。
    默认（都不给）  ：fit='crop' → 最大框组居中（等于"铺满"，无黑边）。
    返回 dict；`valid=False` 时不应导出（源比单屏还小等）。
    """
    if frames:
        return resolve_frames(cols, src_w, src_h, frames)
    n = max(1, int(cols))
    sw, sh = max(2, int(src_w)), max(2, int(src_h))
    canvas_w, canvas_h = canvas_size(n)
    req = None
    if crop:
        req = [int(round(float(v))) for v in crop]
        c = align_crop(req, sw, sh)
        mode = 'crop'
    elif zoom and float(zoom) > 0:
        c = crop_from_zoom(n, sw, sh, zoom, pos)
        mode = 'zoom'
    else:
        c = max_crop(n, sw, sh)
        mode = 'cover'
    x, y, w, h = c
    s = canvas_w / float(w) if w else 1.0
    inside = (x >= 0 and y >= 0 and x + w <= sw and y + h <= sh)
    aspect_ok = (abs(w - n * h) <= 2 and w > 0 and h > 0)
    too_small = (sw < PANEL_W or sh < PANEL_H)
    return {'cols': n, 'canvas_w': canvas_w, 'canvas_h': canvas_h,
            'src_w': sw, 'src_h': sh, 'crop': c, 'crop_requested': req,
            'crop_aligned': bool(req and req != c), 'mode': mode,
            'scale': round(s, 6),                       # 输出像素/源像素
            'src_px_per_out_px': round(w / float(canvas_w), 6),
            'src_px_per_seg_px': round((w / float(n)) / float(PANEL_W), 6),
            'inside': inside, 'aspect_ok': aspect_ok, 'too_small': too_small,
            'valid': inside and aspect_ok and not too_small,
            'seg_w': PANEL_W, 'seg_h': PANEL_H, 'layout': '1x%d' % n}


def build_filter(geo, index):
    """第 index 段（0 基）的滤镜链（**无 pad**）：

    旧口径（无缝）：crop(源裁剪矩形) → scale(画布宽 × 480) → crop(480:480:i*480:0)
                    相邻格之间没有任何被丢弃的列（seam 恒 0）
    每屏独立窗口 ：crop(s:s:x_i:y_i) → scale(480:480)
                    相邻两屏之间可以有缝（缝内画面不输出 = 丢弃）
    """
    if geo.get('mode') == 'frames' and not geo.get('regular'):
        f = geo['frames'][index]
        chain = ['crop=%d:%d:%d:%d' % (f[3], f[3], f[0], f[1])]
        if f[3] != PANEL_W:
            chain.append('scale=%d:%d:flags=lanczos' % (PANEL_W, PANEL_H))
        return ','.join(chain)
    cx, cy, cw, ch = geo['crop']
    canvas_w, canvas_h = geo['canvas_w'], geo['canvas_h']
    x0 = index * PANEL_W
    if x0 + PANEL_W > canvas_w:
        raise ValueError('段序号越界：index=%d cols=%d' % (index, geo['cols']))
    chain = ['crop=%d:%d:%d:%d' % (cw, ch, cx, cy)]
    if cw != canvas_w or ch != canvas_h:
        chain.append('scale=%d:%d:flags=lanczos' % (canvas_w, canvas_h))
    chain.append('crop=%d:%d:%d:0' % (PANEL_W, PANEL_H, x0))
    return ','.join(chain)


def enc_args(fps=None, gop_sec=None, vcodec=None, profile=None, level=None,
             pix_fmt=None, crf=None, preset=None, bitrate=None):
    """统一编码参数（段段完全一致 → 时间轴一致；首帧 IDR；无 B 帧；faststart）"""
    fps = int(fps or ENC['fps'])
    gop_sec = int(gop_sec or ENC['gop_sec'])
    a = ['-c:v', vcodec or ENC['vcodec'], '-profile:v', profile or ENC['profile'],
         '-level', level or ENC['level'], '-pix_fmt', pix_fmt or ENC['pix_fmt'],
         '-r', str(fps), '-g', str(fps * gop_sec), '-bf', str(ENC['bf']),
         '-sc_threshold', '0', '-keyint_min', str(fps * gop_sec)]
    if bitrate:
        a += ['-b:v', bitrate, '-maxrate', bitrate, '-bufsize', '4000k']
    else:
        a += ['-crf', str(crf if crf is not None else ENC['crf'])]
    a += ['-preset', preset or ENC['preset'], '-movflags', ENC['movflags']]
    return a


def encode_segments(src, geo, out_dir, enc_opts=None, audio_index=None, quiet=False):
    """按 geo 把源裁切并切成 N 段（每段 480×480、参数完全一致），写 wall.json，返回 manifest"""
    if not geo.get('valid', True):
        raise ValueError('几何无效，拒绝导出：crop=%s inside=%s aspect_ok=%s too_small=%s' % (
            geo.get('crop'), geo.get('inside'), geo.get('aspect_ok'), geo.get('too_small')))
    o = dict(enc_opts or {})
    fps = int(o.get('fps', ENC['fps']))
    info = stream_info(src)
    os.makedirs(out_dir, exist_ok=True)
    n = geo['cols']
    segs = []
    for i in range(n):
        vf = build_filter(geo, i)
        out = os.path.join(out_dir, 'seg_%d.mp4' % (i + 1))
        cmd = ['ffmpeg', '-y', '-v', 'error', '-i', src, '-vf', vf]
        if audio_index is not None and i == int(audio_index):
            cmd += ['-map', '0:v:0', '-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k', '-shortest']
        else:
            cmd += ['-an']
        cmd += enc_args(fps=fps, gop_sec=o.get('gop_sec'), vcodec=o.get('vcodec'),
                        profile=o.get('profile'), level=o.get('level'),
                        pix_fmt=o.get('pix_fmt'), crf=o.get('crf'),
                        preset=o.get('preset'), bitrate=o.get('bitrate'))
        cmd += [out]
        run(cmd)
        s = stream_info(out)
        kf = keyframe_times(out, limit=4)
        if geo.get('frames'):
            src_crop = list(geo['frames'][i])           # 该屏自己的窗口
        else:
            src_crop = [geo['crop'][0] + i * (geo['crop'][2] // n), geo['crop'][1],
                        geo['crop'][2] // n, geo['crop'][3]]
        segs.append({'index': i + 1, 'file': os.path.basename(out), 'info': s,
                     'first_keyframes': kf, 'filter': vf, 'md5': md5(out),
                     'src_crop': src_crop})
        if not quiet:
            print('  seg_%d.mp4  %dx%d  %s  %s  %d 帧  %.3fs  首关键帧@%s' % (
                i + 1, s['width'], s['height'], s['vcodec'], s['profile'],
                s['nb_frames'], s['duration'], [round(t, 3) for t in kf[:2]]))
    _frames = geo.get('frames')
    _gaps = list(geo.get('gaps') or [])
    manifest = {'source': os.path.basename(src), 'source_path': os.path.abspath(src),
                'source_info': info,
                'mode': 'frames' if _frames else 'crop',   # frames=每屏独立窗口（可留缝）
                'per_screen': bool(_frames),
                'regular': bool(geo.get('regular', True)),
                'frames': [list(f) for f in _frames] if _frames else None,
                'layout': geo['layout'], 'bezel': int(max(_gaps) if _gaps else 0),
                'seam_w': int(max(_gaps) if _gaps else 0),
                'canvas_w': geo['canvas_w'], 'canvas_h': geo['canvas_h'],
                'crop': geo['crop'], 'crop_rect': 'x=%d:y=%d:w=%d:h=%d' % tuple(geo['crop']),
                'crop_requested': geo.get('crop_requested'),
                'crop_aligned': geo.get('crop_aligned'),
                'scale': geo['scale'], 'src_px_per_out_px': geo['src_px_per_out_px'],
                'fit': geo['mode'], 'covered': True, 'gaps': _gaps,
                'gap_px': int(max(_gaps) if _gaps else 0),
                'seg_w': PANEL_W, 'seg_h': PANEL_H,
                'fps': fps, 'gop_sec': int(o.get('gop_sec', ENC['gop_sec'])),
                'codec': o.get('vcodec', ENC['vcodec']),
                'profile': o.get('profile', ENC['profile']),
                'segments': segs}
    with open(os.path.join(out_dir, 'wall.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


# ── v2 组清单（playlist.json）：一个组 = 多个视频（clip）轮播 ────────────────
# 磁盘布局（工具产出 == 设备 /mnt/sdnand/wall/<组名>/）：
#   playlist.json                     v2 清单（本版新增，必须写）
#   c1/seg_1.mp4 … c1/seg_N.mp4       第 1 个视频切成 N 段（每段 480×480）
#   c2/seg_1.mp4 … c2/seg_N.mp4       第 2 个视频（段数同 cols，时长可不同）
#   wall.json                         v1 兼容壳（segments = 第 1 个 clip 的分段）
# playlist.json 字段口径（与设备固件侧严格一致，勿改）：
#   version=2 / group=组名 / n=**组内 clip 数** / cols=每个 clip 的段数（= 屏数）
#   total_ms=Σ(clip.dur_ms) ← 一整轮轮播时长
#   clips[] = {name, dur_ms, segments[{index, file, dur_ms}]}；file 相对组目录
PLAYLIST_NAME = 'playlist.json'
WALL_JSON_NAME = 'wall.json'
CLIP_NAME_MAX = 32
GROUP_NAME_MAX = 48


def sanitize_clip_name(name, fallback='c1'):
    """clip（= 子目录名，必须与 file 前缀一致）：ASCII only，[A-Za-z0-9_.-]，首字符字母/数字"""
    n = re.sub(r'[^A-Za-z0-9_.-]', '_', str(name or '').strip())
    n = n.strip('._-')
    fb = re.sub(r'[^A-Za-z0-9_.-]', '', str(fallback or 'c1')).strip('._-') or 'c1'
    if not n or not re.match(r'^[A-Za-z0-9]', n):
        n = fb if re.match(r'^[A-Za-z0-9]', fb) else 'c1'
    return n[:CLIP_NAME_MAX]


def sanitize_group_name(name, fallback='zksw-wall'):
    """组名（设备上的目录名）：只去掉**路径非法字符**（/ \\ : * ? " < > | 与控制符、空字符），

    中文允许（用户常直接用源片名当组名）；空白折叠成 '-'。空 → fallback。
    """
    n = str(name or '').strip()
    n = re.sub(r'[\x00-\x1f\x7f]', '', n)
    n = re.sub(r'[\\/:*?"<>|]+', '-', n)
    n = re.sub(r'\s+', '-', n)
    n = re.sub(r'-{2,}', '-', n).strip('-. ')
    n = n.strip()
    if not n:
        n = re.sub(r'[\\/:*?"<>|\s]+', '-', str(fallback or '')).strip('-') or 'zksw-wall'
    return n[:GROUP_NAME_MAX]


def unique_clip_name(name, used):
    """组内 clip 名去重：c1 → c1_2 → c1_3 …"""
    base = name
    i = 2
    while name in used:
        name = '%s_%d' % (base, i)
        i += 1
    used.add(name)
    return name


def build_playlist(group, cols, clip_entries):
    """playlist.json v2（键序固定：version/group/n/cols/total_ms/clips）"""
    return {'version': 2, 'group': group, 'n': len(clip_entries), 'cols': int(cols),
            'total_ms': sum(int(c['dur_ms']) for c in clip_entries),
            'clips': clip_entries}


def clip_entry(name, seg_files, seg_durs):
    """一个 clip 的清单项；**同一 clip 内每段 dur_ms 取同一个值**（段必须等长）"""
    d = int(max(seg_durs)) if seg_durs else 0
    return {'name': name, 'dur_ms': d,
            'segments': [{'index': i + 1, 'file': '%s/%s' % (name, f), 'dur_ms': d}
                         for i, f in enumerate(seg_files)]}


def write_playlist(out_dir, playlist):
    p = os.path.join(out_dir, PLAYLIST_NAME)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)
    return p


def build_wall_v1(group, cols, clip_names, clip_mans, clip_entries, playlist, sources):
    """v1 兼容壳（给旧版读者/旧固件）：

      · 段列表 `segments` = **第 1 个 clip** 的分段（旧语义：segments[i] 就是第 i 屏那一段），
        但 file 写成真实相对路径 `c1/seg_i.mp4`；
      · 另加 `seg_ms` = 第一片时长（旧 distribute 直接读它/segments[0] 时长作 sp_wall_seg_ms）、
        `total_ms`、`clips` 概览、`playlist` 指向 v2 清单。
    """
    first = clip_mans[0]
    segs = []
    for s in first['segments']:
        s2 = dict(s)
        s2['file'] = '%s/%s' % (clip_names[0], s['file'])
        segs.append(s2)
    wall = {k: v for k, v in first.items() if k != 'segments'}
    wall['segments'] = segs
    wall['mode'] = 'crop'
    wall['v2'] = True
    wall['playlist'] = PLAYLIST_NAME
    wall['group'] = group
    wall['cols'] = int(cols)
    wall['n'] = len(clip_entries)
    wall['seg_ms'] = int(clip_entries[0]['dur_ms'])
    wall['total_ms'] = int(playlist['total_ms'])
    wall['clips'] = [{'name': clip_names[i], 'dir': clip_names[i],
                      'dur_ms': int(clip_entries[i]['dur_ms']),
                      'segments': len(clip_entries[i]['segments']),
                      'source': os.path.basename(sources[i])}
                     for i in range(len(clip_entries))]
    wall['note'] = ('v2 组清单见 %s；本文件为 v1 兼容壳（segments = 第 1 个 clip 的分段，'
                    'seg_ms = 第一片时长）' % PLAYLIST_NAME)
    return wall


def write_wall_v1(out_dir, wall):
    p = os.path.join(out_dir, WALL_JSON_NAME)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(wall, f, ensure_ascii=False, indent=2)
    return p


def load_group(group_dir):
    """读组清单 → 统一 v2 形状；**旧布局（只有 wall.json、无 playlist.json）也支持**。

    返回 {'version','group','n','cols','total_ms','clips',...,'legacy': bool}
    """
    pp = os.path.join(group_dir, PLAYLIST_NAME)
    if os.path.exists(pp):
        with open(pp, encoding='utf-8') as f:
            pl = json.load(f)
        pl['legacy'] = False
        return pl
    wp = os.path.join(group_dir, WALL_JSON_NAME)
    if not os.path.exists(wp):
        raise FileNotFoundError('既没有 %s 也没有 %s：%s' % (PLAYLIST_NAME, WALL_JSON_NAME, group_dir))
    with open(wp, encoding='utf-8') as f:
        wj = json.load(f)
    segs = wj.get('segments') or []
    durs = [int(round((s.get('info') or {}).get('duration', 0) * 1000)) for s in segs]
    # 旧布局：根目录 seg_1..N 是**同一时刻**各屏那一段（同时播），不是轮播
    #  → 整组就 1 个 clip，时长 = 单片时长（不是 ΣN 个片）
    d = durs[0] if durs else int(wj.get('seg_ms') or 0)
    entries = [{'index': i + 1, 'file': s.get('file') or ('seg_%d.mp4' % (i + 1)),
                'dur_ms': d} for i, s in enumerate(segs)]
    return {'version': 1, 'group': wj.get('group') or os.path.basename(os.path.normpath(group_dir)),
            'n': 1, 'cols': len(entries), 'total_ms': d,
            'clips': [{'name': '', 'dur_ms': d, 'segments': entries}],
            'legacy': True, 'wall_v1': wj}


def parse_clip_crop_specs(specs, k_max):
    """把 `--crop` 规格解析成「逐 clip 的裁剪矩形」列表（长度 k_max，None=该 clip 用默认最大框）。

      '1=128:66:1024:512'（k= 前缀 → 只作用于第 k 个 clip）
      '0:0:960:480'      （无 k= → 作用到所有 clip，可被 k= 覆盖）
    """
    per, default = {}, None
    for s in (specs or []):
        s = str(s).strip()
        if not s:
            continue
        if '=' in s:
            k, v = s.split('=', 1)
            per[int(k.strip())] = _parse_rect(v)
        else:
            default = _parse_rect(s)
    out = [per.get(k, default) for k in range(1, k_max + 1)]
    return out if any(v is not None for v in out) else None


def parse_clip_name_specs(specs, k_max):
    """`--clip-name 1=start,2=intro` → 逐 clip 名字（缺省 None=自动 c1..cK）"""
    per = {}
    for s in (specs or []):
        s = str(s).strip()
        if not s:
            continue
        for part in s.split(','):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            per[int(k.strip())] = v.strip()
    if not per:
        return None
    return [per.get(k) for k in range(1, k_max + 1)]


def _parse_rect(text):
    parts = [float(x) for x in re.split(r'[:,x]', str(text)) if x != '']
    if len(parts) != 4:
        raise SystemExit('[错误] 裁剪矩形需要 x:y:w:h 四个数，如 128:66:1024:512（收到 %r）' % text)
    return parts


def group_encode(sources, cols, out_dir, group='zksw-wall', crops=None, names=None,
                 enc_opts=None, quiet=False, frames=None):
    """**多视频成组**：每个源各自裁剪 + 切成 cols 段 → `<out_dir>/<clip>/seg_i.mp4`，

    写 playlist.json（v2）+ wall.json（v1 兼容壳）。返回结构化结果（CLI/网页共用）。
      crops:  逐 clip 的 [x,y,w,h] 或 None（None=该 clip 默认最大框居中）
      frames: 逐 clip 的 [[x,y,w,h]×N] 或 None（每屏一个独立窗口，可留缝；优先于 crops）
      names:  逐 clip 的名字或 None（None=自动 c1..cK；会清洗 + 去重）
    """
    if not sources:
        raise ValueError('至少需要一个源视频')
    n = max(1, int(cols))
    os.makedirs(out_dir, exist_ok=True)
    used, clip_names, clip_mans, details = set(), [], [], []
    for k, src in enumerate(sources):
        nm = sanitize_clip_name((names or [None] * len(sources))[k] if names and k < len(names)
                                else None, 'c%d' % (k + 1))
        nm = unique_clip_name(nm, used)
        info = stream_info(src)
        crop = None
        fr = None
        if frames and k < len(frames) and frames[k]:
            fr = [[float(v) for v in f] for f in frames[k]]
        elif crops and k < len(crops) and crops[k]:
            crop = [float(v) for v in crops[k]]
        geo = resolve_geometry(n, info['width'], info['height'], crop=crop, frames=fr)
        if not geo['valid']:
            raise ValueError(
                ('第 %d 个视频（%s）：源 %d×%d 小于单屏 %d×%d，无法生成 1:1 的 480×480 分段'
                 % (k + 1, os.path.basename(src), geo['src_w'], geo['src_h'], PANEL_W, PANEL_H))
                if geo['too_small'] else
                ('第 %d 个视频（%s）：裁剪矩形越界或宽高比 ≠ N:1（crop=%s inside=%s aspect_ok=%s）'
                 % (k + 1, os.path.basename(src), geo['crop'], geo['inside'], geo['aspect_ok'])))
        cdir = os.path.join(out_dir, nm)
        if not quiet:
            print('[clip %d/%d] %s ← %s  %d×%d %.3fs' % (
                k + 1, len(sources), nm, os.path.basename(src), info['width'], info['height'],
                info['duration']))
            if geo.get('frames'):
                print('  每屏独立窗口 %d 个（边长 %d，缝 %s px，缩放 %.4f）：%s'
                      % (n, geo['frames'][0][3],
                         '/'.join(str(g) for g in (geo.get('gaps') or [0]))[:40],
                         geo['scale'],
                         ' '.join('P%d(%d,%d)' % (i + 1, f[0], f[1])
                                  for i, f in enumerate(geo['frames']))))
            else:
                print('  裁剪 x=%d y=%d w=%d h=%d → 画布 %d×%d（缩放 %.4f）'
                      % (geo['crop'][0], geo['crop'][1], geo['crop'][2], geo['crop'][3],
                         geo['canvas_w'], geo['canvas_h'], geo['scale']))
        man = encode_segments(src, geo, cdir, enc_opts=enc_opts, quiet=quiet)
        clip_names.append(nm)
        clip_mans.append(man)
        seg_files = [s['file'] for s in man['segments']]
        seg_durs = [int(round(s['info']['duration'] * 1000)) for s in man['segments']]
        jitter = (max(seg_durs) - min(seg_durs)) if seg_durs else 0
        if jitter > 1 and not quiet:
            print('  [警告] 同一 clip 内段时长不一致（max−min=%d ms）：%s' % (jitter, seg_durs))
        entry = clip_entry(nm, seg_files, seg_durs)
        segs_detail = []
        for i, s in enumerate(man['segments']):
            d2 = dict(s)
            d2['file'] = '%s/%s' % (nm, s['file'])
            d2['dur_measured_ms'] = seg_durs[i]
            try:
                d2['bytes'] = os.path.getsize(os.path.join(cdir, s['file']))
            except OSError:
                d2['bytes'] = 0
            segs_detail.append(d2)
        details.append({'name': nm, 'dir': nm, 'source': os.path.basename(src),
                        'source_path': os.path.abspath(src), 'source_info': info,
                        'crop': geo['crop'], 'crop_requested': geo.get('crop_requested'),
                        'scale': geo['scale'], 'canvas_w': geo['canvas_w'],
                        'canvas_h': geo['canvas_h'], 'dur_ms': entry['dur_ms'],
                        'dur_jitter_ms': jitter, 'segments': segs_detail,
                        'frames': geo.get('frames'),
                        'regular': bool(geo.get('regular', True)),
                        'gaps': list(geo.get('gaps') or []),
                        'per_screen': bool(geo.get('frames'))})
        if not quiet:
            print('  → %d 段，时长 %.3fs (=%d ms)' % (len(seg_files), entry['dur_ms'] / 1000.0,
                                                 entry['dur_ms']))

    entries = [clip_entry(clip_names[i], [s['file'] for s in clip_mans[i]['segments']],
                          [d['dur_measured_ms'] for d in details[i]['segments']])
               for i in range(len(clip_names))]
    playlist = build_playlist(group, n, entries)
    pp = write_playlist(out_dir, playlist)
    wall = build_wall_v1(group, n, clip_names, clip_mans, entries, playlist, sources)
    wp = write_wall_v1(out_dir, wall)
    if not quiet:
        print('\n组名 %s　clip 数 %d　每个 clip %d 段（%d×%d）' % (
            group, len(entries), n, PANEL_W, PANEL_H))
        for c in entries:
            print('  %-10s %6.3f s  %d 段  %s' % (
                c['name'], c['dur_ms'] / 1000.0, len(c['segments']),
                ', '.join(s['file'] for s in c['segments'])))
        print('总时长（一整轮）= %d ms = %.3f s' % (playlist['total_ms'], playlist['total_ms'] / 1000.0))
        print('已写出：%s（v2 清单） + %s（v1 兼容壳）' % (pp, wp))
    return {'group': group, 'out_dir': out_dir, 'cols': n, 'n': len(entries),
            'total_ms': playlist['total_ms'], 'clips': details,
            'playlist': playlist, 'wall': wall,
            'playlist_path': pp, 'wall_path': wp}


# ── sample：生成测试用整墙视频 ───────────────────────────────────────────
def cmd_sample(a):
    total_w = PANEL_W * a.cols
    colors = ['0x1E88E5', '0xE53935', '0x43A047', '0x8E24AA', '0xFB8C00', '0x00897B']
    # ① 每屏一个底色源（注意：源之间必须用 ';' 分隔）
    srcs = []
    for i in range(a.cols):
        srcs.append('color=c=%s:s=%dx%d:d=%d:r=%d[bg%d]'
                    % (colors[i % len(colors)], PANEL_W, PANEL_H, a.seconds,
                       ENC['fps'], i))
    stack = (''.join('[bg%d]' % i for i in range(a.cols))
             + 'hstack=inputs=%d[wall]' % a.cols)
    # ② 逐屏叠 Pn 标签 + 全局帧号/时间码（便于肉眼判断是否同一帧）
    chain = []
    prev = '[wall]'
    for i in range(a.cols):
        nxt = '[p%d]' % i
        chain.append("%sdrawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
                     "text='P%d':fontcolor=white:fontsize=130:"
                     "x=%d+(480-text_w)/2:y=26%s" % (prev, i + 1, i * PANEL_W, nxt))
        prev = nxt
    chain.append("%sdrawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
                 "text='%%{eif\\:n\\:d\\:5}':fontcolor=white:fontsize=96:"
                 "x=(w-text_w)/2:y=h-180[fn]" % prev)
    prev = '[fn]'
    chain.append("%sdrawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
                 "text='%%{pts\\:hms}':fontcolor=yellow:fontsize=56:"
                 "x=(w-text_w)/2:y=h-70[tc]" % prev)
    graph = ';'.join(srcs) + ';' + stack + ';' + ';'.join(chain) + ';[tc]copy[v]'
    cmd = ['ffmpeg', '-y', '-v', 'error', '-filter_complex', graph,
           '-map', '[v]', '-c:v', ENC['vcodec'], '-profile:v', ENC['profile'],
           '-level', ENC['level'], '-pix_fmt', ENC['pix_fmt'],
           '-r', str(ENC['fps']), '-g', str(ENC['fps'] * ENC['gop_sec']),
           '-bf', str(ENC['bf']), '-sc_threshold', '0',
           '-crf', str(ENC['crf']), '-preset', ENC['preset'],
           '-movflags', ENC['movflags'], a.out]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    run(cmd)
    print('已生成测试整墙视频: %s (%dx%d, %d 秒)' % (a.out, total_w, PANEL_H, a.seconds))
    print(json.dumps(stream_info(a.out), ensure_ascii=False, indent=1))


# ── split：等分切块 ───────────────────────────────────────────────────
def cmd_split(a):
    """两种模式（2026-09-27 口径③：**已彻底删掉"缝"（bezel）这个概念**）：
      crop   : 默认。N 个相邻 480×480 绿框的并集 = 裁剪窗口，**框外直接丢弃**
      direct : 老式等分（源正好 = N×480×480 时一把切，不做 scale）
    """
    info = stream_info(a.inp)
    src_w, src_h = info['width'], info['height']
    cols = a.cols
    mode = a.mode
    if mode == 'crop':
        return cmd_split_crop(a, info)
    if src_w != PANEL_W * cols or src_h != PANEL_H:
        print('[警告] 源视频 %dx%d 与期望的 %dx%d 不一致（仍按等分切）' % (
            src_w, src_h, PANEL_W * cols, PANEL_H))
    seg_w = src_w // cols
    os.makedirs(a.out_dir, exist_ok=True)
    manifest = {'source': os.path.abspath(a.inp), 'source_info': info,
                'layout': '%dx1' % cols, 'seg_w': seg_w, 'seg_h': src_h,
                'fps': a.fps or ENC['fps'], 'gop_sec': a.gop_sec, 'codec': a.vcodec,
                'profile': a.profile, 'segments': []}
    for i in range(cols):
        out = os.path.join(a.out_dir, 'seg_%d.mp4' % (i + 1))
        vf = 'crop=%d:%d:%d:0' % (seg_w, src_h, i * seg_w)
        cmd = ['ffmpeg', '-y', '-v', 'error', '-i', a.inp,
               '-vf', vf,
               '-c:v', a.vcodec, '-profile:v', a.profile, '-level', a.level,
               '-pix_fmt', a.pix_fmt, '-r', str(a.fps), '-g', str(a.fps * a.gop_sec),
               '-bf', '0', '-sc_threshold', '0', '-keyint_min', str(a.fps * a.gop_sec)]
        if a.bitrate:
            cmd += ['-b:v', a.bitrate, '-maxrate', a.bitrate, '-bufsize', str(int(float(a.bitrate[:-1] if a.bitrate.endswith('k') else float(a.bitrate) / 1000) * 2)) + 'k']
        else:
            cmd += ['-crf', str(a.crf)]
        if a.audio_index is not None and i == a.audio_index:
            cmd += ['-map', '0:v:0', '-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k',
                    '-shortest']
        else:
            cmd += ['-an']
        cmd += ['-preset', a.preset, '-movflags', '+faststart', out]
        run(cmd)
        s = stream_info(out)
        kf = keyframe_times(out, limit=4)
        manifest['segments'].append({'index': i + 1, 'file': os.path.basename(out),
                                     'info': s, 'first_keyframes': kf,
                                     'md5': md5(out)})
        print('  seg_%d.mp4  %dx%d  %s  %s  %d 帧  %.3fs  首关键帧@%s' % (
            i + 1, s['width'], s['height'], s['vcodec'], s['profile'],
            s['nb_frames'], s['duration'], kf[:2]))
    with open(os.path.join(a.out_dir, 'wall.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print('已写出清单: %s' % os.path.join(a.out_dir, 'wall.json'))
    print('目标机目录建议: /mnt/sdnand/wall/<组名>/seg_1..N.mp4（联动资源与屏保资源分开）')


def cmd_split_crop(a, info):
    """2026-09-27 口径③：绿框裁剪（默认，无缝、无 pad、无黑边）

    源上取一块矩形（`--crop x:y:w:h` 直接给，或 `--zoom`/`--pos` 反推，或默认最大框组居中）
    → scale 到画布宽×480 → 每格裁 480×480。
    """
    cols = max(1, int(a.cols))
    crop = None
    if a.crop:
        parts = [float(x) for x in re.split(r'[:,x]', a.crop) if x != '']
        if len(parts) != 4:
            print('[错误] --crop 需要 x:y:w:h 四个数，如 --crop 128:66:1024:512')
            raise SystemExit(2)
        crop = parts
    pos = None
    if a.pos:
        p = [float(x) for x in re.split(r'[:,]', a.pos) if x != '']
        if len(p) != 2:
            print('[错误] --pos 需要 x:y 两个数（框组中心在源上的坐标）')
            raise SystemExit(2)
        pos = p
    geo = resolve_geometry(cols, info['width'], info['height'], crop=crop,
                           zoom=a.zoom or 0, pos=pos)
    print('[裁剪] 源 %d×%d  框组 %d 格 → 画布 %d×%d  缩放(输出/源) %.4f  裁剪矩形 x=%d y=%d w=%d h=%d'
          % (geo['src_w'], geo['src_h'], geo['cols'], geo['canvas_w'], geo['canvas_h'],
             geo['scale'], geo['crop'][0], geo['crop'][1], geo['crop'][2], geo['crop'][3]))
    if geo['crop_aligned'] and not a.quiet:
        print('[提示] crop 对齐到偶数后生效：请求 %s → 实际 %s'
              % (geo['crop_requested'], geo['crop']))
    if not geo['valid']:
        print('[拒绝导出] %s' % ('源视频小于单屏 %d×%d（当前 %d×%d），无法生成 1:1 的 480×480 分段；请换更高分辨率素材'
                                % (PANEL_W, PANEL_H, geo['src_w'], geo['src_h'])
                                if geo['too_small'] else
                                '裁剪矩形越界或宽高比 ≠ N:1：crop=%s inside=%s aspect_ok=%s'
                                % (geo['crop'], geo['inside'], geo['aspect_ok'])))
        raise SystemExit(3)
    man = encode_segments(a.inp, geo, a.out_dir, enc_opts={
        'fps': a.fps, 'gop_sec': a.gop_sec, 'vcodec': a.vcodec, 'profile': a.profile,
        'level': a.level, 'pix_fmt': a.pix_fmt, 'crf': a.crf, 'preset': a.preset,
        'bitrate': a.bitrate}, audio_index=a.audio_index, quiet=bool(a.quiet))
    print('已写出清单: %s' % os.path.join(a.out_dir, 'wall.json'))
    print('目标机目录建议: /mnt/sdnand/wall/<组名>/seg_1..N.mp4（联动资源与屏保资源分开）')
    return man


def md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ── verify：校验一致性 ────────────────────────────────────────────────
def cmd_verify(a):
    files = sorted([os.path.join(a.dir, f) for f in os.listdir(a.dir)
                    if f.startswith('seg_') and f.endswith('.mp4')],
                   key=lambda p: int(''.join(c for c in os.path.basename(p) if c.isdigit()) or 0))
    if not files:
        print('目录里没有 seg_*.mp4')
        return
    rows = []
    ok = True
    base = None
    for p in files:
        s = stream_info(p)
        first_kf, pts = first_keyframe_pts(p)
        rows.append((s, first_kf, pts))
        if base is None:
            base = s
        else:
            for k in ('width', 'height', 'vcodec', 'profile', 'level', 'pix_fmt', 'fps',
                      'nb_frames', 'duration'):
                if s[k] != base[k]:
                    ok = False
                    print('[不一致] %s 的 %s: %s != %s' % (s['file'], k, s[k], base[k]))
        if not first_kf or abs(pts) > 0.001:
            ok = False
            print('[警告] %s 首帧不是 IDR/首帧 pts 非 0（%s @ %.3f）' % (s['file'], first_kf, pts))
    print('\n%-12s %-11s %-7s %-6s %-6s %-6s %-9s %-8s %s' % (
        'file', 'res', 'codec', 'prof', 'fps', 'frames', 'duration', 'firstK', 'audio'))
    for s, kf, pts in rows:
        print('%-12s %-11s %-7s %-6s %-6s %-6d %-9.3f %-8s %s' % (
            s['file'], '%dx%d' % (s['width'], s['height']), s['vcodec'], s['profile'],
            s['fps'], s['nb_frames'], s['duration'], 'IDR' if kf else 'NO', s['audio']))
    print('\n%s' % ('[OK] 所有段参数完全一致、首帧均为 IDR、帧数与时长相同 —— 可上机做帧同步'
                    if ok else '[X] 存在不一致，见上方提示'))


def cmd_group(a):
    """多视频成组：一个组 = 多个视频（clip）轮播（playlist.json v2）"""
    srcs = list(a.srcs or [])
    if not srcs:
        print('[错误] 至少给一个源视频：--in a.mp4 --in b.mp4 或 --src a.mp4 b.mp4')
        raise SystemExit(2)
    cols = max(1, int(a.cols))
    crops = parse_clip_crop_specs(a.crop, len(srcs))
    names = parse_clip_name_specs(a.clip_name, len(srcs))
    group = sanitize_group_name(a.group_name or '',
                               fallback=os.path.splitext(os.path.basename(srcs[0]))[0])
    if a.group_name and group != a.group_name:
        print('[提示] 组名清洗：%r → %r（去掉路径非法字符）' % (a.group_name, group))
    print('源 %d 个　分割数量 cols=%d　组名 %s　输出 %s' % (len(srcs), cols, group, a.out_dir))
    res = group_encode(srcs, cols, a.out_dir, group=group, crops=crops, names=names,
                       enc_opts={'fps': a.fps, 'gop_sec': a.gop_sec, 'vcodec': a.vcodec,
                                 'profile': a.profile, 'level': a.level, 'pix_fmt': a.pix_fmt,
                                 'crf': a.crf, 'preset': a.preset, 'bitrate': a.bitrate},
                       quiet=bool(a.quiet))
    print('目标机目录约定: /mnt/sdnand/wall/%s/{playlist.json,wall.json,c1/seg_1..N.mp4,…}'
          % res['group'])
    return res


def main():
    ap = argparse.ArgumentParser(description='多屏拼接切块工具（ffmpeg）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s1 = sub.add_parser('sample', help='生成测试整墙视频')
    s1.add_argument('--out', default='sample_wall.mp4')
    s1.add_argument('--cols', type=int, default=2)
    s1.add_argument('--seconds', type=int, default=20)
    s1.set_defaults(func=cmd_sample)

    s2 = sub.add_parser('split', help='把整墙视频等分成 N 段')
    s2.add_argument('--in', dest='inp', required=True)
    s2.add_argument('--cols', type=int, default=2)
    s2.add_argument('--out-dir', default='wall_out')
    s2.add_argument('--vcodec', default=ENC['vcodec'])
    s2.add_argument('--profile', default=ENC['profile'])
    s2.add_argument('--level', default=ENC['level'])
    s2.add_argument('--pix-fmt', dest='pix_fmt', default=ENC['pix_fmt'])
    s2.add_argument('--fps', type=int, default=ENC['fps'])
    s2.add_argument('--gop-sec', dest='gop_sec', type=int, default=ENC['gop_sec'])
    s2.add_argument('--crf', type=int, default=ENC['crf'])
    s2.add_argument('--bitrate', default=None, help='例 3000k（给了就走码率优先）')
    s2.add_argument('--preset', default=ENC['preset'])
    s2.add_argument('--audio-index', dest='audio_index', type=int, default=None,
                    help='只让第 N 段（0 基）带音频，其它段静音；不给=全部静音')
    s2.add_argument('--mode', choices=['crop', 'direct'], default='crop',
                    help='crop=绿框裁剪（默认：框内=导出，无缝、无 pad）；'
                         'direct=源正好 N×480 时直接等分（不做 scale）')
    s2.add_argument('--zoom', type=float, default=0,
                    help='crop 模式：缩放（输出像素/源像素）；>1 放大框更小，<1 缩小框更大；0=最大框组')
    s2.add_argument('--pos', default=None,
                    help='crop 模式：框组中心在源上的坐标 x:y（默认居中）')
    s2.add_argument('--crop', default=None,
                    help='crop 模式：直接指定源裁剪矩形 x:y:w:h（须 w = N×h），优先于 --zoom/--pos')
    s2.add_argument('--quiet', action='store_true', help='不打印每段明细')
    s2.set_defaults(func=cmd_split)

    s3 = sub.add_parser('verify', help='校验段参数一致性')
    s3.add_argument('--dir', required=True)
    s3.set_defaults(func=cmd_verify)

    s4 = sub.add_parser('group', help='一个组 = 多个视频轮播（各 clip 长短可不同；写 playlist.json v2）')
    s4.add_argument('--in', dest='srcs', action=_SrcList, help='源视频（可重复：--in a.mp4 --in b.mp4）')
    s4.add_argument('--src', dest='srcs', action=_SrcList, nargs='+',
                    help='源视频（一次多个：--src a.mp4 b.mp4 c.mp4）')
    s4.add_argument('--cols', type=int, default=2, help='每个 clip 切成几段 = 屏数（默认 2）')
    s4.add_argument('--group-name', dest='group_name', default='zksw-wall',
                    help='组名（设备上 /mnt/sdnand/wall/<组名>/；非法字符会清洗）')
    s4.add_argument('--clip-name', dest='clip_name', action='append', default=None,
                    help='逐 clip 改名：--clip-name 1=start,2=intro（缺省自动 c1..cK）')
    s4.add_argument('--crop', action='append', default=None,
                    help='逐 clip 裁剪矩形：--crop k=x:y:w:h（k 从 1 起）；不带 k= → 作用所有 clip；'
                         '缺省 = 各 clip 自己的最大框居中')
    s4.add_argument('--out-dir', default='group_out')
    s4.add_argument('--vcodec', default=ENC['vcodec'])
    s4.add_argument('--profile', default=ENC['profile'])
    s4.add_argument('--level', default=ENC['level'])
    s4.add_argument('--pix-fmt', dest='pix_fmt', default=ENC['pix_fmt'])
    s4.add_argument('--fps', type=int, default=ENC['fps'])
    s4.add_argument('--gop-sec', dest='gop_sec', type=int, default=ENC['gop_sec'])
    s4.add_argument('--crf', type=int, default=ENC['crf'])
    s4.add_argument('--bitrate', default=None, help='例 3000k（给了就走码率优先）')
    s4.add_argument('--preset', default=ENC['preset'])
    s4.add_argument('--quiet', action='store_true', help='不打印每段明细')
    s4.set_defaults(func=cmd_group)

    a = ap.parse_args()
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        sys.stderr.write('缺少 ffmpeg/ffprobe，请先安装并加入 PATH\n')
        raise SystemExit(1)
    a.func(a)


if __name__ == '__main__':
    main()
