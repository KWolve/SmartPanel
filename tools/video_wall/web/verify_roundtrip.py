#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_roundtrip.py — 「绿框所见 = 导出内容」验收（两种独立方法 + 边界/无黑边）

背景（钟工 2026-09-27 11:55）：上一版「计算刚好偏差了」，且不该有橙色缝。
本脚本给出可复现证据，证明：**绿框里显示什么，导出的那段就是什么**（同一时间点逐像素对齐），
且**框外丢弃、无橙色缝、无黑边**。

方法①（源侧独立复算，不经 UI/不经 split_wall.build_filter）：
    PIL 独立把源帧按同一个 crop 矩形裁剪 → 缩放到 N×480 → 切片，与导出段首帧逐像素比对。
    · 控制组 A：ffmpeg 独立跑同一条链（手写 crop/scale/crop）vs PIL → 只反映"重采样器差异"。
方法②（所见侧 = 用户真正看到的）：
    headless 系统浏览器（web/shoot_box.mjs，Node+CDP）把网页预览里**绿框区域 1:1** 截出来
    （注入 CSS 把画布钉在页面 (0,0)、K 调到"绿框宽度 == N×480 CSS px"），
    与"导出段首帧横排"比对 → 证明所见即所出。
边界/无黑边：
    把框贴到视频四角（含右下角贴边）导出，量测每段**最外 2px** 的亮度并与源对应位置比对 → 不为 0。

用法： python web/verify_roundtrip.py [--keep] [--port 8798] [--src-grid-only]
输出： out/_evidence/verify_seen_vs_exported.json（+ preview_box.png / export_hstack.png / 源帧）
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import split_wall as sw  # noqa: E402

EVID = os.path.join(TOOLS, 'out', '_evidence')
TMP = os.path.join(TOOLS, 'temp_verify')
SRC_DIR = os.path.join(TOOLS, 'out', '_src')
PANEL = 480
PORT = 8798
BASE = 'http://127.0.0.1:%d' % PORT

# 容忍阈值：这一路有①重采样器差异（浏览器/PIL/ffmpeg 各自不同）+②x264 crf20 有损编码，
# 所以不是 0；下面的数字是"合成硬边缘测试图"上的实测上界（报告里同时给出分解）。
TOL = {'mean': 6.0, 'p99': 22.0, 'max': 90.0, 'pct_gt8': 3.0}   # pct_gt8 单位 %
fails = []


def ff(args, timeout=1200):
    p = subprocess.run(['ffmpeg'] + list(args), capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError('ffmpeg 失败: %s\n%s' % (' '.join(args), p.stderr.decode('utf-8', 'replace')[-1500:]))
    return p.stdout


def check(name, cond, detail=''):
    print('  %s %-58s %s' % ('[OK]  ' if cond else '[FAIL]', name, detail))
    if not cond:
        fails.append('%s %s' % (name, detail))
    return bool(cond)


# ── 图像工具（纯标准库）────────────────────────────────────────────────
def frame_rgb(path, t=0.0, timeout=600):
    """抽一帧 → (bytes rgb24, w, h)"""
    info = sw.stream_info(path)
    raw = ff(['-v', 'error', '-ss', str(t), '-i', path, '-frames:v', '1',
              '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], timeout=timeout)
    w, h = info['width'], info['height']
    assert len(raw) >= w * h * 3, '抽帧字节不足'
    return raw[:w * h * 3], w, h


def hstack_rgb(paths, t=0.0):
    """多段首帧横排 → (bytes rgb24, w, h)"""
    args = ['-y', '-v', 'error']
    for p in paths:
        args += ['-ss', str(t), '-i', p]
    fc = ''.join('[%d:v]' % i for i in range(len(paths))) + 'hstack=inputs=%d[v]' % len(paths)
    args += ['-filter_complex', fc, '-map', '[v]', '-frames:v', '1',
             '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = ff(args, timeout=600)
    info = sw.stream_info(paths[0])
    w, h = info['width'] * len(paths), info['height']
    return raw[:w * h * 3], w, h


def diff(a, b, w, h):
    """逐像素（RGB）差值统计；a/b 为 rgb24 bytes"""
    ds = []
    for i in range(0, min(len(a), len(b))):
        ds.append(abs(a[i] - b[i]))
    ds.sort()
    n = len(ds)
    return {
        'pixels': w * h, 'mean': round(sum(ds) / float(n), 3),
        'p50': ds[n // 2], 'p99': ds[int(n * 0.99)], 'max': ds[-1],
        'pct_gt8': round(100.0 * sum(1 for d in ds if d > 8) / n, 3),
        'pct_gt20': round(100.0 * sum(1 for d in ds if d > 20) / n, 3),
    }


def luma(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def slice_cols(buf, W, H, x0, w):
    """从 W×H 的 rgb24 缓冲里取出列区间 [x0, x0+w)（逐行拷，不能用连续字节切片！）"""
    out = bytearray(w * H * 3)
    for y in range(H):
        src = (y * W + x0) * 3
        dst = y * w * 3
        out[dst:dst + w * 3] = buf[src:src + w * 3]
    return bytes(out)


def edge_stats_rgb(buf, w, h, band=2):
    """最外 band 像素的平均亮度（RGB→luma）"""
    tot = cnt = 0.0
    for y in range(h):
        for x in list(range(0, band)) + list(range(w - band, w)):
            o = (y * w + x) * 3
            tot += luma(buf[o], buf[o + 1], buf[o + 2]); cnt += 1
    top = bot = 0.0
    for y in list(range(0, band)) + list(range(h - band, h)):
        for x in range(w):
            o = (y * w + x) * 3
            v = luma(buf[o], buf[o + 1], buf[o + 2])
            if y < band:
                top += v
            else:
                bot += v
    return {'left_right2': round(tot / cnt, 2),
            'top_bottom2': round((top + bot) / (2.0 * band * w), 2)}


def edge_bands_rgb(buf, w, h, band=2):
    """四边最外 band 的平均亮度：{top,bottom,left,right}"""
    out = {}
    for k, rows, cols in (('top', range(band), range(w)),
                          ('bottom', range(h - band, h), range(w))):
        t = c = 0.0
        for y in rows:
            for x in cols:
                o = (y * w + x) * 3
                t += luma(buf[o], buf[o + 1], buf[o + 2]); c += 1
        out[k] = round(t / c, 2)
    for k, cols in (('left', range(band)), ('right', range(w - band, w))):
        t = c = 0.0
        for y in range(h):
            for x in cols:
                o = (y * w + x) * 3
                t += luma(buf[o], buf[o + 1], buf[o + 2]); c += 1
        out[k] = round(t / c, 2)
    return out


# ── 测试源：带刻度 / 色块 / 帧号（帧间还会动）──────────────────────────
def build_grid_src(path, w=1280, h=720, fps=25, dur=2):
    font = 'C\\:/Windows/Fonts/consolab.ttf'
    vf = ','.join([
        'drawbox=x=0:y=0:w=320:h=180:color=0xE53935@1:t=fill',
        'drawbox=x=960:y=0:w=320:h=180:color=0x43A047@1:t=fill',
        'drawbox=x=0:y=540:w=320:h=180:color=0x1E88E5@1:t=fill',
        'drawbox=x=960:y=540:w=320:h=180:color=0x8E24AA@1:t=fill',
        'drawbox=x=340:y=200:w=600:h=320:color=0xF5F5F5@1:t=fill',
        'drawgrid=w=40:h=40:t=1:c=0x000000@0.55',          # 40px 刻度网格
        'drawgrid=w=160:h=160:t=2:c=0x000000@0.85',        # 160px 粗网格
        "drawbox=x='mod(t*640\\,1240)':y=30:w=40:h=40:color=0xFF00FF@1:t=fill",  # 运动块（帧间可区分）
        "drawtext=fontfile='%s':text='F%%{eif\\:n\\:d\\:4}':fontcolor=0x102030:fontsize=64:x=360:y=240" % font,
        "drawtext=fontfile='%s':text='%%{pts\\:hms}':fontcolor=0x102030:fontsize=40:x=360:y=430" % font,
        "drawtext=fontfile='%s':text='FRAME':fontcolor=0x102030:fontsize=40:x=40:y=200" % font,
        # 最后画上 24px 亮边框（红/绿/黄/蓝）——保证**帧的最外像素是亮的**，
        # 这样"框贴边导出"时才能用亮度直接判定"到底有没有黑边"
        'drawbox=x=0:y=0:w=%d:h=24:color=0xE53935@1:t=fill' % w,
        'drawbox=x=0:y=%d:w=%d:h=24:color=0x43A047@1:t=fill' % (h - 24, w),
        'drawbox=x=0:y=0:w=24:h=%d:color=0xFFD12D@1:t=fill' % h,
        'drawbox=x=%d:y=0:w=24:h=%d:color=0x2DA8FF@1:t=fill' % (w - 24, h),
    ])
    ff(['-y', '-v', 'error', '-f', 'lavfi', '-i',
        'color=c=0x2B3A4A:s=%dx%d:r=%d:d=%d' % (w, h, fps, dur), '-vf', vf,
        '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv420p',
        '-r', str(fps), '-g', str(fps), '-bf', '0', '-movflags', '+faststart', path], timeout=900)
    return path


# ── HTTP ──────────────────────────────────────────────────────────────
def http_get(p, raw=False):
    with urllib.request.urlopen(BASE + p, timeout=600) as r:
        b = r.read()
        return r.status, (b if raw else json.loads(b.decode('utf-8')))


def http_post(p, obj, timeout=2400):
    q = urllib.request.Request(BASE + p, data=json.dumps(obj).encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(q, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


def split_via_api(src_name, cols, crop):
    st, j = http_post('/api/split', {'file': src_name, 'cols': cols, 'crop': list(crop)})
    if not j.get('ok'):
        raise RuntimeError('导出失败: %s' % j.get('error'))
    grp = j['group']
    d = os.path.join(TOOLS, 'out', grp)
    return grp, d, j


# ── 方法①：PIL 独立复算 ────────────────────────────────────────────────
def pil_reference(src_png_bytes_or_path, crop, cols, seg_w=PANEL, seg_h=PANEL):
    """PIL：crop(源矩形) → 缩放到 cols*480 × 480；返回整条 + 每段切片 bytes"""
    from PIL import Image
    if isinstance(src_png_bytes_or_path, bytes):
        import io as _io
        im = Image.open(_io.BytesIO(src_png_bytes_or_path)).convert('RGB')
    else:
        im = Image.open(src_png_bytes_or_path).convert('RGB')
    x, y, w, h = crop
    full = im.crop((x, y, x + w, y + h)).resize((cols * seg_w, seg_h), Image.LANCZOS)
    segs = []
    for i in range(cols):
        segs.append(full.crop((i * seg_w, 0, (i + 1) * seg_w, seg_h)).tobytes())
    return full.tobytes(), segs


def src_frame_png(src, t=0.0):
    return ff(['-v', 'error', '-ss', str(t), '-i', src, '-frames:v', '1',
               '-f', 'image2pipe', '-vcodec', 'png', '-'], timeout=600)


def ffmpeg_chain_raw(src, crop, cols, t=0.0):
    """控制组 A：手写一条 crop→scale（不经 split_wall.build_filter）"""
    x, y, w, h = crop
    vf = 'crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos' % (w, h, x, y, cols * PANEL, PANEL)
    return ff(['-v', 'error', '-ss', str(t), '-i', src, '-vf', vf, '-frames:v', '1',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], timeout=600)


# ── 主流程 ────────────────────────────────────────────────────────────
def main():
    global PORT, BASE
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--port', type=int, default=PORT)
    ap.add_argument('--src', default=None, help='用已有源（默认自动生成网格测试源）')
    ap.add_argument('--no-shot', action='store_true', help='跳过方法②（headless 截图）')
    a = ap.parse_args()
    PORT = a.port
    BASE = 'http://127.0.0.1:%d' % PORT
    os.makedirs(EVID, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(SRC_DIR, exist_ok=True)

    rep = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'port': PORT,
           'tolerance': TOL, 'checks': []}

    print('=== 0. 测试源（刻度 / 色块 / 帧号 / 运动块；无损）===')
    src = a.src
    if not src:
        src = os.path.join(TMP, 'grid_1280x720.mp4')
        build_grid_src(src)
    name = os.path.basename(src)
    shutil.copyfile(src, os.path.join(SRC_DIR, name))
    si = sw.stream_info(src)
    print('  %s  %dx%d  %s 帧  %.2fs  无损(qp0)' % (name, si['width'], si['height'],
                                                 si['nb_frames'], si['duration']))

    proc = subprocess.Popen([sys.executable, os.path.join(HERE, 'server.py'),
                             '--host', '127.0.0.1', '--port', str(PORT)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            try:
                http_get('/api/list'); break
            except Exception:
                time.sleep(0.4)

        # ── 主用 crop：非平凡位置 + 非 1.0 缩放（K=15/16，且 x/y*K 为整数便于 1:1 截图）──
        cols = 2
        crop = [128, 64, 1024, 512]
        assert crop[2] == cols * crop[3], '测试 crop 必须 w = N×h'
        print('\n=== 1. 主用例：cols=%d  crop=%s（非居中、非 1:1 缩放）===' % (cols, crop))
        grp, out_dir, j = split_via_api(name, cols, crop)
        man = j['manifest']
        print('  实际生效 crop=%s（请求 %s）  scale=%s  组=%s' % (
            j['crop_effective'], j['crop_requested'], man['scale'], grp))
        check('后端原样使用 crop（请求==生效）',
              list(j['crop_requested']) == list(j['crop_effective']),
              '%s vs %s' % (j['crop_requested'], j['crop_effective']))
        check('每段 480×480', all(s['info']['width'] == PANEL and s['info']['height'] == PANEL
                                for s in man['segments']))
        check('滤镜链无 pad', all('pad=' not in s['filter'] for s in man['segments']),
              man['segments'][0]['filter'])

        seg_paths = [os.path.join(out_dir, s['file']) for s in man['segments']]

        # ── 方法①：PIL 独立复算 ──
        print('\n=== 2. 方法①：PIL 独立复算（源帧 crop→scale→切片）vs 导出段首帧 ===')
        src_png = src_frame_png(src, 0)
        open(os.path.join(EVID, 'src_frame0.png'), 'wb').write(src_png)
        ref_full, ref_segs = pil_reference(src_png, crop, cols)
        rows = []
        for i, sp in enumerate(seg_paths):
            buf, w, h = frame_rgb(sp, 0)
            d = diff(ref_segs[i], buf, w, h)
            rows.append({'seg': 'seg_%d.mp4' % (i + 1), 'diff': d})
            print('    seg_%d：mean %.3f  p99 %d  max %d  >8 占 %.3f%%' % (
                i + 1, d['mean'], d['p99'], d['max'], d['pct_gt8']))
        worst = max(r['diff']['mean'] for r in rows)
        check('方法① 平均差 ≤ %.1f（重采样器+PIL对比）' % TOL['mean'], worst <= TOL['mean'],
              'worst mean=%.3f' % worst)
        check('方法① p99 ≤ %d' % TOL['p99'], all(r['diff']['p99'] <= TOL['p99'] for r in rows),
              'p99=%s' % [r['diff']['p99'] for r in rows])
        rep['checks'].append({'name': '方法① PIL 独立复算 vs 导出段首帧', 'crop': crop,
                             'cols': cols, 'group': grp, 'segments': rows,
                             'worst_mean': worst})
        # 控制组 A：重采样器差异（ffmpeg 手写链 vs PIL）
        A = ffmpeg_chain_raw(src, crop, cols, 0)
        dA = diff(ref_full, A, cols * PANEL, PANEL)
        print('    控制组A（ffmpeg 手写链 vs PIL，仅重采样器差异）：mean %.3f  max %d'
              % (dA['mean'], dA['max']))
        rep['checks'].append({'name': '控制组A 重采样器差异（ffmpeg vs PIL）', 'diff': dA})

        # ── 2b. 每屏独立窗口（可留缝）：每段 = 它自己那个窗口的内容 ──
        print('\n=== 2b. 每屏独立窗口（中间留 40px 缝）：每段 = 该屏自己窗口的内容 ===')
        fcase = [[200, 80, 520, 520], [760, 120, 520, 520]]         # 两屏各自摆位、中间 40px 缝
        st, jg = http_post('/api/group_split',
                           {'clips': [{'file': name, 'name': 'p1', 'frames': fcase}],
                            'cols': 2, 'group_name': 'verify-frames'})
        check('每屏窗口导出成功', jg.get('ok') is True, str(jg.get('error'))[:120])
        cg = (jg.get('clips') or [{}])[0]
        check('后端原样使用每屏窗口', cg.get('frames') == fcase, str(cg.get('frames')))
        check('缝 40px 记在清单里', list(cg.get('gaps') or []) == [40], str(cg.get('gaps')))
        check('per_screen=True / regular=False', cg.get('per_screen') is True
              and cg.get('regular') is False)
        from PIL import Image
        gdir = os.path.join(TOOLS, 'out', jg['group'])
        im0 = Image.open(io.BytesIO(src_png)).convert('RGB')
        rowsF, refs = [], []
        for i, f in enumerate(fcase):
            sp = os.path.join(gdir, cg['segments'][i]['file'])
            buf, w, h = frame_rgb(sp, 0)
            ref = im0.crop((f[0], f[1], f[0] + f[2], f[1] + f[3])).resize((PANEL, PANEL),
                                                                        Image.LANCZOS).tobytes()
            d = diff(ref, buf, PANEL, PANEL)
            refs.append((ref, buf))
            rowsF.append({'seg': i + 1, 'frame': f, 'diff': d})
            print('    P%d 窗口 [%d,%d,%d,%d] → seg_%d：mean %.3f  p99 %d  max %d' % (
                i + 1, f[0], f[1], f[2], f[3], i + 1, d['mean'], d['p99'], d['max']))
        wmean = max(r['diff']['mean'] for r in rowsF)
        check('每屏 所见=所出（mean ≤ %.1f）' % TOL['mean'], wmean <= TOL['mean'],
              'worst mean=%.3f' % wmean)
        check('每屏 p99 ≤ %d' % TOL['p99'], all(r['diff']['p99'] <= TOL['p99'] for r in rowsF),
              'p99=%s' % [r['diff']['p99'] for r in rowsF])
        # 缝确实被跳过：seg_2 拿"无缝位置（x=720）"的内容对不上，拿自己的窗口（x=760）才对得上
        f2 = fcase[1]
        ref_wrong = im0.crop((f2[0] - 40, f2[1], f2[0] - 40 + f2[2],
                              f2[1] + f2[3])).resize((PANEL, PANEL), Image.LANCZOS).tobytes()
        d_bad = diff(ref_wrong, refs[1][1], PANEL, PANEL)
        print('    缝自检：拿"若无缝应从 x=%d 起"的画面比 seg_2：mean %.3f（应显著更大）'
              % (f2[0] - 40, d_bad['mean']))
        check('缝真的被跳过（无缝位置对不上）',
              d_bad['mean'] > 3 * max(rowsF[1]['diff']['mean'], 0.6),
              'wrong=%.3f vs right=%.3f' % (d_bad['mean'], rowsF[1]['diff']['mean']))
        check('每段仍 480×480 / 无 pad', all('pad=' not in s['filter'] for s in cg['segments'])
              and all(s['info']['width'] == PANEL and s['info']['height'] == PANEL
                      for s in cg['segments']))
        rep['checks'].append({'name': '每屏独立窗口（缝 40px）：每段 = 自己窗口', 'frames': fcase,
                              'group': jg['group'], 'segments': rowsF,
                              'seam_skip_wrong_mean': d_bad['mean']})

        # ── 2c. 每屏窗口越界 → 钳制回源内（结构上不可能黑边）──
        st, jc = http_post('/api/group_split',
                           {'clips': [{'file': name, 'name': 'p1',
                                       'frames': [[-50, -40, 520, 520], [1000, 400, 520, 520]]}],
                            'cols': 2, 'group_name': 'verify-clamp'})
        cf = (jc.get('clips') or [{}])[0]
        okc = jc.get('ok') is True and all(
            f[0] >= 0 and f[1] >= 0 and f[0] + f[2] <= si['width'] and f[1] + f[3] <= si['height']
            for f in (cf.get('frames') or []))
        print('  [%s] 越界窗口 → 钳制在源内   %s' % ('OK' if okc else 'FAIL', cf.get('frames')))
        check('每屏窗口越界 → 钳制回源内（无黑边）', okc, str(cf.get('frames')))
        rep['checks'].append({'name': '每屏窗口越界→钳制', 'frames': cf.get('frames')})

        # ── 方法②：headless 截图绿框区域 ──
        if not a.no_shot:
            print('\n=== 3. 方法②：headless 浏览器截"绿框内画面" vs 导出段首帧横排 ===')
            K = (cols * PANEL) / float(crop[2])                    # 目标：绿框宽 = N×480 CSS px
            vieww = round(si['width'] * K)
            q = ('?src=%s&cols=%d&crop=%s&overlay=0&bare=1&t=0' %
                 (urllib.parse.quote(name), cols, ','.join(str(v) for v in crop)))
            url = BASE + '/' + q
            shot = os.path.join(EVID, 'preview_box.png')
            cmd = ['node', os.path.join(HERE, 'shoot_box.mjs'), '--url', url,
                   '--vieww', str(vieww), '--out', shot, '--expect', '%dx%d' % (cols * PANEL, PANEL),
                   '--viewport', '1500x1000', '--wait', '40000']
            p = subprocess.run(cmd, capture_output=True, timeout=300)
            so = p.stdout.decode('utf-8', 'replace').strip().splitlines()
            sj = {}
            try:
                sj = json.loads(so[-1]) if so else {}
            except Exception:
                sj = {}
            print('    shot_box: %s' % json.dumps(sj, ensure_ascii=False)[:300])
            if not sj.get('ok'):
                check('方法② headless 截图成功', False, p.stderr.decode('utf-8', 'replace')[-300:])
            else:
                check('截图 clip 为整数像素（无半像素重采样）', sj.get('integerClip') is True,
                      str(sj.get('fractionalKeys')))
                check('截图尺寸 = %dx%d' % (cols * PANEL, PANEL), sj.get('expectMatch') is True,
                      str(sj.get('clip')))
                from PIL import Image
                im = Image.open(shot).convert('RGB')
                if im.size != (cols * PANEL, PANEL):
                    check('截图尺寸（PIL 实测）', False, str(im.size))
                else:
                    cur = im.tobytes()
                    hb, hw, hh = hstack_rgb(seg_paths, 0)
                    d2 = diff(cur, hb, hw, hh)
                    print('    绿框截图 vs 导出段横排：mean %.3f  p99 %d  max %d  >8 占 %.3f%%'
                          % (d2['mean'], d2['p99'], d2['max'], d2['pct_gt8']))
                    check('方法② 平均差 ≤ %.1f（所见=所出）' % TOL['mean'], d2['mean'] <= TOL['mean'],
                          'mean=%.3f' % d2['mean'])
                    check('方法② p99 ≤ %d' % TOL['p99'], d2['p99'] <= TOL['p99'], 'p99=%d' % d2['p99'])
                    # 逐段切片比对（比整排更严格：能抓出"整体错位"）
                    rows2 = []
                    for i in range(cols):
                        b2 = slice_cols(cur, cols * PANEL, PANEL, i * PANEL, PANEL)
                        b3 = slice_cols(hb, cols * PANEL, PANEL, i * PANEL, PANEL)
                        d3 = diff(b2, b3, PANEL, PANEL)
                        rows2.append({'seg': i + 1, 'diff': d3})
                        print('      seg_%d：mean %.3f p99 %d' % (i + 1, d3['mean'], d3['p99']))
                    # 错位灵敏度（自检：把截图右移 2px，diff 必须显著变大 → 证明比对有分辨力）
                    W_, H_ = cols * PANEL, PANEL
                    dsh = diff(slice_cols(cur, W_, H_, 2, W_ - 2), slice_cols(hb, W_, H_, 0, W_ - 2),
                               W_ - 2, H_)
                    print('    灵敏度自检（截图右移 2px）：mean %.3f（应显著大于上面的均值）'
                          % dsh['mean'])
                    check('比对有分辨力（错位 2px 差异明显更大）', dsh['mean'] > 3 * max(d2['mean'], 0.6),
                          'shifted=%.3f vs normal=%.3f' % (dsh['mean'], d2['mean']))
                    rep['checks'].append({'name': '方法② headless 绿框截图 vs 导出段首帧',
                                          'shot_box': sj, 'diff_all': d2, 'segments': rows2,
                                          'shift2px_mean': dsh['mean'], 'vieww': vieww, 'K': K})
                    hb_png = os.path.join(EVID, 'export_hstack.png')
                    args = ['-y', '-v', 'error']
                    for pp in seg_paths:
                        args += ['-ss', '0', '-i', pp]
                    args += ['-filter_complex', ''.join('[%d:v]' % i for i in range(cols)) +
                             'hstack=inputs=%d[v]' % cols, '-map', '[v]', '-frames:v', '1', hb_png]
                    ff(args)

        if not a.no_shot:
            print('\n=== 3b. 交互自检（真发鼠标/滚轮事件：拖框 = 移框组、滚轮 = 缩放、钳制在视频内）===')
            p3 = subprocess.run(['node', os.path.join(HERE, 'shoot_box.mjs'), '--url', url,
                                 '--vieww', str(vieww), '--selftest'], capture_output=True, timeout=300)
            so3 = p3.stdout.decode('utf-8', 'replace').strip().splitlines()
            try:
                sj3 = json.loads(so3[-1]) if so3 else {}
            except Exception:
                sj3 = {}
            for st in sj3.get('steps', []):
                check('交互：' + st.get('name', '?'), st.get('pass') is True, str(st.get('detail', ''))[:130])
            if not sj3.get('steps'):
                check('交互自检有输出', False, p3.stderr.decode('utf-8', 'replace')[-200:])
            rep['checks'].append({'name': '交互自检（拖框/滚轮/钳制）', 'result': sj3})

        # ── 边界 / 无黑边：框贴四角 ──
        print('\n=== 4. 边界：框贴到视频角落（最外 2px 必须还是源画面，不能是黑边）===')
        corners = [('左上角贴边', [0, 0, 960, 480]), ('右下角贴边', [320, 240, 960, 480])]
        crow = []
        for tag, c in corners:
            g2, d2, j2 = split_via_api(name, 2, c)
            seg2 = [os.path.join(d2, s['file']) for s in j2['manifest']['segments']]
            ref2_full, ref2 = pil_reference(src_png, c, 2)      # PIL 独立复算（含源边缘真值）
            # 这个 crop 里哪些边是"视频最外沿"（= 导出若合成黑边，这些边一定是黑的）
            bd = {'left': c[0] == 0, 'top': c[1] == 0,
                  'right': c[0] + c[2] == si['width'], 'bottom': c[1] + c[3] == si['height']}
            rows3 = []
            for i, sp in enumerate(seg2):
                buf, w, h = frame_rgb(sp, 0)
                d3 = diff(ref2[i], buf, w, h)
                es = edge_bands_rgb(buf, w, h, 2)
                ers = edge_bands_rgb(ref2[i], w, h, 2)
                need = [k for k in ('top', 'bottom') if bd[k]]
                if bd['left'] and i == 0:
                    need.append('left')
                if bd['right'] and i == len(seg2) - 1:
                    need.append('right')
                devs = {k: round(abs(es[k] - ers[k]), 3) for k in ('top', 'bottom', 'left', 'right')}
                rows3.append({'seg': 'seg_%d.mp4' % (i + 1), 'border_bands': need,
                              'edges_luma': es, 'edges_luma_ref': ers, 'edge_dev': devs,
                              'diff_vs_ref': d3,
                              'min_border_luma': min([es[k] for k in need]) if need else None,
                              'min_border_luma_ref': min([ers[k] for k in need]) if need else None})
                print('    %s seg_%d：边缘亮度 上%.1f 下%.1f 左%.1f 右%.1f（源期望 上%.1f 下%.1f 左%.1f 右%.1f）需验边 %s'
                      % (tag, i + 1, es['top'], es['bottom'], es['left'], es['right'],
                         ers['top'], ers['bottom'], ers['left'], ers['right'], need or '-'))
            check('%s：视频最外沿的 2px = 源画面（亮，≥60 luma）—— 无黑边' % tag,
                  all(r['min_border_luma'] is not None and r['min_border_luma'] >= 60.0
                      and r['min_border_luma_ref'] >= 60.0 for r in rows3),
                  'min=%s 源min=%s' % ([r['min_border_luma'] for r in rows3],
                                    [r['min_border_luma_ref'] for r in rows3]))
            check('%s：段序正确（与源同位置逐像素对齐）' % tag,
                  all(r['diff_vs_ref']['mean'] <= TOL['mean'] for r in rows3),
                  'mean=%s' % [r['diff_vs_ref']['mean'] for r in rows3])
            # 边缘像素级：导出段最外 2px 与源参考的最外 2px 差值
            edge_dev = []
            for r in rows3:
                edge_dev.append(max(r['edge_dev'].values()))
            check('%s：边缘亮度与源一致（偏差 ≤ 2 luma，像素级）' % tag,
                  max(edge_dev) <= 2.0, 'max_dev=%.2f' % max(edge_dev))
            crow.append({'corner': tag, 'crop': c, 'group': g2, 'segments': rows3,
                         'edge_max_dev': round(max(edge_dev), 3)})
        rep['checks'].append({'name': '边界 / 无黑边（贴角导出）', 'corners': crow})

        # ── 段一致性（参数/首帧 IDR）──
        print('\n=== 5. 段一致性（参数完全一致 / 首帧 IDR / 帧数时长相同）===')
        for tag, dpath in (('主用例', out_dir),):
            v = []
            files = sorted([os.path.join(dpath, f) for f in os.listdir(dpath)
                            if f.startswith('seg_') and f.endswith('.mp4')])
            base = sw.stream_info(files[0])
            all_same = all(all(sw.stream_info(p)[k] == base[k] for k in
                               ('width', 'height', 'vcodec', 'profile', 'pix_fmt', 'fps',
                                'nb_frames', 'duration')) for p in files)
            idrs = [sw.first_keyframe_pts(p) for p in files]
            check('%s：段参数完全一致' % tag, all_same)
            check('%s：首帧全为 IDR 且 pts=0' % tag,
                  all(k and abs(t) < 1e-3 for k, t in idrs), str(idrs))
            check('%s：+faststart（moov 前置）' % tag,
                  all(open(p, 'rb').read(2048).find(b'moov') >= 0 or
                      open(p, 'rb').read(65536).find(b'moov') <
                      open(p, 'rb').read(65536).find(b'mdat') for p in files), 'moov<mdat')
            rep['checks'].append({'name': '段一致性 %s' % tag, 'all_same': all_same,
                                  'first_keyframes': idrs})

        rp = os.path.join(EVID, 'verify_seen_vs_exported.json')
        with open(rp, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, indent=2)
        print('\n报告: %s' % rp)
        print('\n=== 总判定: %s ===' % ('[PASS] 所见=所出（两种独立方法）+ 无黑边 + 段一致'
                                     if not fails else '[FAIL]\n  - ' + '\n  - '.join(fails)))
        return 0 if not fails else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        if not a.keep:
            shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
