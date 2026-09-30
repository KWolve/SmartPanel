#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck_crop.py — 绿框裁剪（无缝、无 pad、无黑边）程序化验收（CLI 侧）

背景（钟工 2026-09-27 11:55 口径③）：**绿框 = 唯一裁剪窗口；没有"缝"（bezel）这个概念**。
本脚本用合成源跑完整 CLI 流程并程序化量测：

  A. 无黑边：把框贴边/铺满/取中，对每段导出量测**最外 2px 亮度**（明亮源 ≥60，纯黑≈16）
  B. 分区无缝（替代旧的"缝丢弃"检查）：用无损灰阶 ramp 源逐列比对"实测 vs 几何预测"，
     并验证 seg_i 末列 → seg_{i+1} 首列 只差**一个正常采样步长**（1 个源像素跨度），
     而不再是被丢弃的 2b 画布像素（旧口径会丢 41 画布 px）
  C. 段参数完全一致 / 首帧 IDR / 帧数与时长相同
  D. 结构保证：滤镜链里**没有 pad**，几何里 bezel 恒 0（"缝"概念已删除）

用法： python selfcheck_crop.py [--keep]        （默认跑完删临时媒体，保留报告+证据图）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import split_wall as sw  # noqa: E402

TMP = os.path.join(HERE, 'temp_check')
EVID = os.path.join(HERE, 'out', '_evidence')
BLACK_LIMIT = 60.0        # 边缘 2px 平均亮度 < 60 视为"黑边"（纯黑≈16，明亮源≈90+）


def ff(args, timeout=900):
    p = subprocess.run(['ffmpeg'] + list(args), capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace')[-1200:])
    return p.stdout


def gray_frame(path, t=0.5):
    """抽一帧 → 灰度二维数组（list of bytes 行），用于像素量测"""
    raw = ff(['-v', 'error', '-ss', str(t), '-i', path, '-frames:v', '1',
              '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], timeout=300)
    info = sw.stream_info(path)
    w, h = info['width'], info['height']
    if len(raw) < w * h:
        raise RuntimeError('抽帧字节数不足: %d < %d' % (len(raw), w * h))
    return [raw[y * w:(y + 1) * w] for y in range(h)], w, h


def mean(vals):
    return sum(vals) / float(len(vals)) if vals else 0.0


def edge_stats(path, t=0.0):
    """上下左右最外 2px 行/列的平均亮度（0~255）"""
    g, w, h = gray_frame(path, t)
    return {
        'top2': round(mean([v for y in (0, 1) for v in g[y]]), 2),
        'bottom2': round(mean([v for y in (h - 2, h - 1) for v in g[y]]), 2),
        'left2': round(mean([g[y][x] for y in range(h) for x in (0, 1)]), 2),
        'right2': round(mean([g[y][x] for y in range(h) for x in (w - 2, w - 1)]), 2),
    }


def src_profile(path, t=0.0):
    """源图每列的平均亮度 → 查表用（配无损源，可反推几何）"""
    g, w, h = gray_frame(path, t)
    return [mean([g[y][x] for y in range(h)]) for x in range(w)]


def prof_at(prof, sx):
    """列剖面线性插值（亚像素）"""
    if sx <= 0:
        return prof[0]
    if sx >= len(prof) - 1:
        return prof[-1]
    i = int(sx)
    f = sx - i
    return prof[i] * (1 - f) + prof[i + 1] * f


def canvas_col_to_src(geo, index, col):
    """输出 seg_{index}（0 基）第 col 列 → 源图 x（几何反推，含中心采样修正）"""
    cx = geo['crop'][0]
    canvas_w = geo['canvas_w']
    x0 = index * sw.PANEL_W                      # 无缝：第 i 格起点 = i×480
    return cx + (x0 + col + 0.5) * (geo['crop'][2] / float(canvas_w)) - 0.5


# ── 测试源 ──────────────────────────────────────────────────────────
def build_sources():
    os.makedirs(TMP, exist_ok=True)
    enc = sw.enc_args()
    srcs = {}
    # ① 明亮渐变 + 四边彩色亮边框（最外 24px 是亮的 → 任何"外侧黑边"都能量出来）
    p = os.path.join(TMP, 'bright_1920x1080.mp4')
    vf = ('drawgrid=w=80:h=80:t=2:c=0x000000@0.35,'
          'drawbox=x=0:y=0:w=1920:h=24:color=0xFF2D2D@1:t=fill,'
          'drawbox=x=0:y=1056:w=1920:h=24:color=0x2DFF8A@1:t=fill,'
          'drawbox=x=0:y=0:w=24:h=1080:color=0xFFD12D@1:t=fill,'
          'drawbox=x=1896:y=0:w=24:h=1080:color=0x2DA8FF@1:t=fill')
    ff(['-y', '-v', 'error', '-f', 'lavfi',
        '-i', 'gradients=s=1920x1080:c0=0x3060C0:c1=0xE0D040:x0=0:y0=0:x1=1920:y1=1080:d=3:r=25',
        '-vf', vf] + enc + [p])
    srcs['bright'] = p
    # ② 水平灰阶 ramp（0→255）：验证"每段覆盖的源区间"与几何预测一致、且无缝
    #    ⚠ 必须无损（qc 0 / 444），否则 x264 会把斜级量化成台阶，量测精度全丢
    p = os.path.join(TMP, 'ramp_1920x1080.mp4')
    ff(['-y', '-v', 'error', '-f', 'lavfi', '-i',
        "nullsrc=s=1920x1080:r=25:d=3,geq=lum='255*X/(W-1)':cb=128:cr=128",
        '-c:v', 'libx264', '-profile:v', 'high444', '-pix_fmt', 'yuv444p', '-qp', '0',
        '-r', '25', '-g', '25', '-bf', '0', '-movflags', '+faststart', p])
    srcs['ramp'] = p
    return srcs


def do_split(src, cols, out_name, **kw):
    info = sw.stream_info(src)
    geo = sw.resolve_geometry(cols, info['width'], info['height'], **kw)
    out = os.path.join(TMP, out_name)
    man = sw.encode_segments(src, geo, out, quiet=True)
    return geo, out, man


def verify_consistency(out):
    files = sorted([os.path.join(out, f) for f in os.listdir(out)
                    if f.startswith('seg_') and f.endswith('.mp4')],
                   key=lambda p: int(''.join(c for c in os.path.basename(p) if c.isdigit())))
    keys = ('width', 'height', 'vcodec', 'profile', 'level', 'pix_fmt', 'fps',
            'nb_frames', 'duration')
    diffs, idr = [], []
    base = sw.stream_info(files[0])
    for p in files:
        s = sw.stream_info(p)
        for k in keys:
            if s[k] != base[k]:
                diffs.append('%s.%s=%s≠%s' % (os.path.basename(p), k, s[k], base[k]))
        kf, pts = sw.first_keyframe_pts(p)
        idr.append({'file': os.path.basename(p), 'first_is_IDR': bool(kf), 'pts': pts})
    return {'files': [os.path.basename(f) for f in files], 'base': base,
            'param_diffs': diffs, 'first_frames': idr,
            'all_idr_first': all(x['first_is_IDR'] and abs(x['pts']) < 1e-3 for x in idr),
            'all_same': not diffs}


def evidence_png(out, man, tag, t=0.5):
    """把各段首帧横排拼回整墙 → 证据图（无缝：相邻段直接贴，没有丢弃列）"""
    segs = [os.path.join(out, 'seg_%d.mp4' % (i + 1)) for i in range(len(man['segments']))]
    args = ['-y', '-v', 'error']
    for p in segs:
        args += ['-ss', str(t), '-i', p]
    fc = ''.join('[%d:v]' % i for i in range(len(segs))) + 'hstack=inputs=%d[v]' % len(segs)
    png = os.path.join(EVID, 'crop_check_%s.png' % tag)
    args += ['-filter_complex', fc, '-map', '[v]', '-frames:v', '1', png]
    ff(args, timeout=300)
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true', help='保留临时媒体')
    a = ap.parse_args()
    os.makedirs(EVID, exist_ok=True)
    rep = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'checks': []}
    ok_all = True

    print('=== 生成测试源 ===')
    srcs = build_sources()
    for k, v in srcs.items():
        print('  %-10s %s' % (k, v))

    # ── A. 无黑边（明亮源）：铺满 / 贴左上角 / 贴右下角 / 居中任意框 ──
    cases = [('铺满最大框 N=2', 2, {'fit': 'crop'}),
             ('铺满最大框 N=3', 3, {'fit': 'crop'}),
             ('贴左上角 N=2', 2, {'crop': [0, 0, 960, 480]}),
             ('贴右下角 N=2', 2, {'crop': [960, 600, 960, 480]}),
             ('居中任意框 N=2', 2, {'crop': [256, 128, 1024, 512]})]
    for n, (tag, cols, kw) in enumerate(cases):
        print('\n=== A. 无黑边检查：%s（源 bright 1920x1080）===' % tag)
        geo, out, man = do_split(srcs['bright'], cols, 'bright_%d_%d' % (n, cols), **kw)
        print('  crop=%s  scale=%s  canvas=%dx%d' % (man['crop'], man['scale'],
                                                  man['canvas_w'], man['canvas_h']))
        rows, okc = [], True
        for s in man['segments']:
            es = edge_stats(os.path.join(out, s['file']))
            bad = [k for k, v in es.items() if v < BLACK_LIMIT]
            okc &= not bad
            rows.append({'seg': s['file'], 'res': '%dx%d' % (s['info']['width'], s['info']['height']),
                         'edges': es, 'black_edges': bad})
            print('    %-10s %-9s 上%6.2f 下%6.2f 左%6.2f 右%6.2f  %s' % (
                s['file'], rows[-1]['res'], es['top2'], es['bottom2'], es['left2'], es['right2'],
                'OK 无黑边' if not bad else '✗ 黑边: %s' % bad))
        v = verify_consistency(out)
        png = evidence_png(out, man, 'case%d_n%d' % (n, cols))
        print('  段参数一致=%s  首帧全 IDR=%s  证据图=%s' % (v['all_same'], v['all_idr_first'], png))
        ok_all &= okc and v['all_same'] and v['all_idr_first']
        rep['checks'].append({'name': 'A 无黑边 %s' % tag, 'crop': man['crop'],
                              'scale': man['scale'], 'segments': rows,
                              'no_black_edges': okc, 'threshold': BLACK_LIMIT,
                              'verify': v, 'evidence_png': png})

    # ── B. 分区无缝：ramp 源逐列比对 + 段边界只差一个采样步长 ──
    prof = src_profile(srcs['ramp'])
    print('\n=== B. 分区/无缝检查：N=2（源 ramp 0~255 水平灰阶，无损）===')
    geo, out, man = do_split(srcs['ramp'], 2, 'ramp_n2', fit='crop')
    errs, first, last = [], [], []
    for i in range(2):
        sg, w, h = gray_frame(os.path.join(out, 'seg_%d.mp4' % (i + 1)))
        for col in range(480):
            measured = mean([sg[y][col] for y in range(h)])
            errs.append(abs(measured - prof_at(prof, canvas_col_to_src(geo, i, col))))
        first.append(round(mean([sg[y][0] for y in range(h)]), 2))
        last.append(round(mean([sg[y][479] for y in range(h)]), 2))
    mae = round(sum(errs) / len(errs), 3)
    step_src = geo['crop'][2] / float(geo['canvas_w'])          # 一个输出列 = 多少源像素
    pred_jump = round(abs(prof_at(prof, canvas_col_to_src(geo, 1, 0)) -
                          prof_at(prof, canvas_col_to_src(geo, 0, 479))), 3)
    print('  crop=%s  scale=%s  canvas=%d  一个输出列=%.2f 源像素' % (
        man['crop'], man['scale'], man['canvas_w'], step_src))
    print('  逐列对比（960 列全量）：实测 vs 几何预测 MAE = %.3f luma' % mae)
    print('  seg_1 末列 %.2f / seg_2 首列 %.2f → 跳变 %.2f luma（预测 %.2f = 相邻采样步长，'
          '无丢弃列）' % (last[0], first[1], first[1] - last[0], pred_jump))
    print('  对比旧口径：seg_2 首列曾是画布 x=480+2b（b=20 时丢弃 41 画布 px）→ 现在已经没有这一截')
    okB = mae <= 2.0 and abs((first[1] - last[0]) - pred_jump) <= 1.0
    ok_all &= okB
    rep['checks'].append({'name': 'B 分区无缝 N=2', 'crop': man['crop'], 'scale': man['scale'],
                          'canvas_w': man['canvas_w'], 'col_mae_luma': mae, 'cols_compared': len(errs),
                          'seg1_last_col': last[0], 'seg2_first_col': first[1],
                          'jump_luma': round(first[1] - last[0], 2),
                          'predicted_jump_luma': pred_jump,
                          'one_output_col_src_px': round(step_src, 3),
                          'no_dropped_columns': True})

    # ── C. 结构：滤镜链无 pad；几何 bezel 恒 0 ──
    print('\n=== C. 结构检查：无 pad / 缝≡0（默认无缝口径；每屏独立窗口与"屏缝"见 verify_roundtrip 2b/2c）===')
    no_pad = all('pad=' not in s['filter'] for s in man['segments'])
    filt = [s['filter'] for s in man['segments']]
    print('  filters: %s' % filt)
    okC = no_pad and man.get('bezel') == 0 and man.get('seam_w') == 0
    ok_all &= okC
    rep['checks'].append({'name': 'C 无 pad / bezel≡0', 'filters': filt, 'no_pad': no_pad,
                          'bezel': man.get('bezel'), 'seam_w': man.get('seam_w')})

    rep_path = os.path.join(EVID, 'selfcheck_crop_report.json')
    with open(rep_path, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print('\n报告: %s' % rep_path)
    print('\n=== 总判定: %s ===' % ('[PASS] 无黑边 + 分区无缝（无丢弃列）+ 段参数一致 + 首帧 IDR'
                                 if ok_all else '[FAIL] 见上方明细'))
    if not a.keep:
        shutil.rmtree(TMP, ignore_errors=True)
        print('临时媒体已清理（--keep 可保留）')
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
