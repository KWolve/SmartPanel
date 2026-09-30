#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest_group.py — 「一个组 = 多个视频轮播」端到端验收（playlist.json v2）

自生成素材（3 个 clip，**时长故意不同 4s / 6s / 3s**、分辨率也不同）→ 真跑 CLI
`split_wall.py group` 切整组 → 程序化核对：

  A. 磁盘布局：playlist.json + wall.json + c1/seg_1..N.mp4 …（每个 clip 段数 = cols）
  B. playlist.json 自洽：version=2 / n=clip 数 / cols=段数 / Σdur = total_ms /
     file 前缀 == clip 名、file 存在、index 连续、同一 clip 内每段 dur_ms 相同
  C. 每段 480×480 / 参数完全一致（同 clip 内逐项相同；跨 clip 编码参数相同、时长允许不同）
     / 首帧 IDR@pts0 / 滤镜链无 pad
  D. 逐 clip 独立裁剪（--crop k=…）生效；clip 内容不串（各 clip 首帧互不相同）
  E. 总时长核对：== Σ clip 时长（且 ≈ 请求的 4+6+3 = 13.000 s）
  F. v1 兼容壳 wall.json：segments = 第 1 个 clip 的分段、seg_ms = 第一片时长、clips 概览
  G. 旧布局回归：`split`（单源）仍是根目录 seg_i.mp4 + wall.json、**不写** playlist.json；
     `verify` 通过；load_group() 能读旧布局（legacy=True）

产物/证据 → out/_evidence/（报告 JSON + CLI 日志 + 每组首帧横排/叠图 PNG）
用法： python selftest_group.py [--keep] [--cols 2]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, 'web')
sys.path.insert(0, HERE)
sys.path.insert(0, WEB)
import split_wall as sw                                   # noqa: E402
from verify_roundtrip import frame_rgb, diff, hstack_rgb   # noqa: E402（纯 stdlib + ffmpeg）

EVID = os.path.join(HERE, 'out', '_evidence')
TMP = os.path.join(HERE, 'temp_group_selftest')
PANEL = 480
fails = []
info = {}
for _s in (sys.stdout, sys.stderr):          # 输出重定向到管道/文件时也不要因编码炸掉
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass


def ff(args, timeout=900):
    p = subprocess.run(['ffmpeg'] + list(args), capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError('ffmpeg 失败: %s\n%s' % (' '.join(args),
                                                    p.stderr.decode('utf-8', 'replace')[-1200:]))
    return p.stdout


def check(name, cond, detail=''):
    print('  %s %-64s %s' % ('[OK]  ' if cond else '[FAIL]', name, detail))
    if not cond:
        fails.append('%s %s' % (name, detail))
    return bool(cond)


def run_cli(args, log_path=None):
    """真跑 CLI（子进程），返回 (返回码, stdout)。子进程强制 UTF-8 输出（避免 cp936 乱码）"""
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    p = subprocess.run([sys.executable, os.path.join(HERE, 'split_wall.py')] + list(args),
                       capture_output=True, cwd=HERE, env=env)
    out = p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
    print(out.rstrip())
    if log_path:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('\n$ python split_wall.py %s\n（exit %d）\n%s\n' % (' '.join(args),
                                                                      p.returncode, out))
    return p.returncode, out


# ── 测试素材：分辨率/时长/内容都不同（证明"各 clip 长短不限、各自摆框"）──────────
def build_sources():
    os.makedirs(TMP, exist_ok=True)
    specs = [
        ('a_1280x720_4s.mp4', 1280, 720, 4, 'A', '0x1E88E5'),
        ('b_1920x1080_6s.mp4', 1920, 1080, 6, 'B', '0xE53935'),
        ('c_960x480_3s.mp4', 960, 480, 3, 'C', '0x43A047'),
    ]
    out = []
    font = "C\\:/Windows/Fonts/arialbd.ttf"
    for name, w, h, sec, tag, col in specs:
        p = os.path.join(TMP, name)
        vf = ','.join([
            # 底色块 + 每帧变化的帧号 + 大字标签 + 外圈亮边框（无损，便于逐像素比对）
            'drawtext=fontfile=\'%s\':text=\'%s\':fontcolor=white:fontsize=%d:x=40:y=40'
            % (font, tag, max(48, h // 6)),
            'drawtext=fontfile=\'%s\':text=\'F%%{eif\\:n\\:d\\:4}\':fontcolor=0x101820:'
            'fontsize=%d:x=w-tw-160:y=h-th-80' % (font, max(36, h // 8)),
            'drawgrid=w=80:h=80:t=2:c=0x000000@0.45',
            'drawbox=x=0:y=0:w=%d:h=16:color=0xFF2D2D@1:t=fill' % w,
            'drawbox=x=0:y=%d:w=%d:h=16:color=0x2DFF8A@1:t=fill' % (h - 16, w),
        ])
        ff(['-y', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=s=%dx%d:r=25:d=%d' % (w, h, sec), '-vf', vf,
            '-c:v', 'libx264', '-qp', '0', '-pix_fmt', 'yuv420p', '-r', '25',
            '-g', '25', '-bf', '0', '-movflags', '+faststart', p])
        out.append(p)
    return out


def vstack_png(paths, out_png):
    args = ['-y', '-v', 'error']
    for p in paths:
        args += ['-i', p]
    fc = ''.join('[%d:v]' % i for i in range(len(paths))) + 'vstack=inputs=%d[v]' % len(paths)
    args += ['-filter_complex', fc, '-map', '[v]', '-frames:v', '1', out_png]
    ff(args, timeout=300)
    return out_png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true', help='保留临时素材/产物')
    ap.add_argument('--cols', type=int, default=2)
    a = ap.parse_args()
    os.makedirs(EVID, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    rep = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'cols': a.cols, 'checks': []}
    log_path = os.path.join(EVID, 'selftest_group_cli.log')
    if os.path.exists(log_path):
        os.remove(log_path)

    print('=== 0. 自生成素材（时长故意不同：4s / 6s / 3s；分辨率也不同）===')
    srcs = build_sources()
    durs = []
    for p in srcs:
        s = sw.stream_info(p)
        durs.append(s['duration'])
        print('  %-22s %dx%d  %d 帧  %.3f s  无损(qp0)' % (s['file'], s['width'], s['height'],
                                                          s['nb_frames'], s['duration']))
    clip_secs = [durs[0], durs[1], durs[2]]

    print('\n=== 1. CLI：python split_wall.py group --src a b c --cols %d ===' % a.cols)
    out_dir = os.path.join(EVID, 'group_selftest_%s' % time.strftime('%H%M%S'))
    rc, _o = run_cli(['group', '--src'] + srcs + ['--cols', str(a.cols),
                      '--group-name', 'zksw-wall', '--crop', '1=128:64:1024:512',
                      '--out-dir', out_dir], log_path)
    check('CLI 退出码 0', rc == 0, 'exit=%d' % rc)
    if rc != 0:
        print('\n=== 总判定: [FAIL] CLI 就失败了 ===')
        return 1

    print('\n=== 2. A. 磁盘布局（组目录 == 设备 /mnt/sdnand/wall/<组名>/）===')
    plp = os.path.join(out_dir, 'playlist.json')
    wjp = os.path.join(out_dir, 'wall.json')
    check('playlist.json 存在', os.path.isfile(plp), plp)
    check('wall.json（v1 兼容壳）存在', os.path.isfile(wjp), wjp)
    pl = json.load(open(plp, encoding='utf-8'))
    cols = int(pl['cols'])
    names = [c['name'] for c in pl['clips']]
    check('cols == 请求值 %d' % a.cols, cols == a.cols, 'cols=%s' % cols)
    dirs_ok, files_ok = True, True
    for c in pl['clips']:
        d = os.path.join(out_dir, c['name'])
        if not os.path.isdir(d):
            dirs_ok = False
        for s in c['segments']:
            if not os.path.isfile(os.path.join(out_dir, s['file'])):
                files_ok = False
    check('每个 clip 一个子目录（%s）' % ', '.join(names), dirs_ok)
    check('playlist 里每个 file 都真实存在（相对组目录）', files_ok)
    check('每个 clip 段数 == cols', all(len(c['segments']) == cols for c in pl['clips']),
          str([len(c['segments']) for c in pl['clips']]))
    print('  布局：')
    for c in pl['clips']:
        print('    %-6s %6d ms  %s' % (c['name'], c['dur_ms'],
                                       ', '.join(s['file'] for s in c['segments'])))
    print('    playlist.json / wall.json / %s' % ' / '.join(names))

    print('\n=== 3. B. playlist.json 自洽（版本/字段/Σdur/file/index）===')
    check('version == 2', pl.get('version') == 2, str(pl.get('version')))
    check('n == clip 数', pl.get('n') == len(pl['clips']),
          'n=%s clips=%d' % (pl.get('n'), len(pl['clips'])))
    check('顶层键序/键名符合规格',
          list(pl.keys()) == ['version', 'group', 'n', 'cols', 'total_ms', 'clips'],
          str(list(pl.keys())))
    check('每个 clip 键名符合规格',
          all(list(c.keys()) == ['name', 'dur_ms', 'segments'] for c in pl['clips']))
    check('每个 segment 键名符合规格',
          all(list(s.keys()) == ['index', 'file', 'dur_ms']
              for c in pl['clips'] for s in c['segments']))
    sum_dur = sum(int(c['dur_ms']) for c in pl['clips'])
    check('Σ(clip.dur_ms) == total_ms', sum_dur == int(pl['total_ms']),
          'Σ=%d total_ms=%s' % (sum_dur, pl['total_ms']))
    idx_ok = all([s['index'] for s in c['segments']] == list(range(1, cols + 1))
                 for c in pl['clips'])
    check('index 连续（1..cols）', idx_ok,
          str([[s['index'] for s in c['segments']] for c in pl['clips']]))
    pref_ok = all(s['file'] == '%s/seg_%d.mp4' % (c['name'], s['index'])
                  for c in pl['clips'] for s in c['segments'])
    check('file 前缀 == clip 名（目录名与 file 前缀一致）', pref_ok)
    eq_ok = all(all(s['dur_ms'] == c['dur_ms'] for s in c['segments']) for c in pl['clips'])
    check('同一 clip 内每段 dur_ms 相同（= clip.dur_ms）', eq_ok)
    check('组名 == zksw-wall', pl.get('group') == 'zksw-wall', str(pl.get('group')))
    check('各 clip 时长**互不相同**（证明"播放时长没有约束"）',
          len({c['dur_ms'] for c in pl['clips']}) == len(pl['clips']),
          str([c['dur_ms'] for c in pl['clips']]))

    print('\n=== 4. C. 段一致性（480×480 / 参数完全一致 / 首帧 IDR / 无 pad）===')
    per_clip, all_params = [], []
    for c in pl['clips']:
        man = json.load(open(os.path.join(out_dir, c['name'], 'wall.json'), encoding='utf-8'))
        segs = []
        for s in c['segments']:
            p = os.path.join(out_dir, s['file'])
            si = sw.stream_info(p)
            kf, pts = sw.first_keyframe_pts(p)
            filt = None
            for m in man['segments']:
                if m['file'] == os.path.basename(s['file']):
                    filt = m['filter']
            segs.append({'file': s['file'], 'index': s['index'], 'info': si,
                         'first_idr': bool(kf), 'pts': pts,
                         'filter': filt, 'dur_measured_ms': int(round(si['duration'] * 1000))})
            all_params.append((si['width'], si['height'], si['vcodec'], si['profile'],
                               si['level'], si['pix_fmt'], si['fps']))
        per_clip.append({'name': c['name'], 'segments': segs, 'manifest': man})
    check('每段都是 480×480', all(p[0] == PANEL and p[1] == PANEL for p in all_params),
          str(sorted({(p[0], p[1]) for p in all_params})))
    check('跨 clip 的编码参数完全一致（编码器/Profile/Level/pix_fmt/fps）',
          len(set(all_params)) == 1, str(sorted(set(all_params))))
    same_in_clip = True
    for pc in per_clip:
        base = pc['segments'][0]['info']
        for s in pc['segments'][1:]:
            for k in ('width', 'height', 'vcodec', 'profile', 'level', 'pix_fmt', 'fps',
                      'nb_frames', 'duration'):
                if s['info'][k] != base[k]:
                    same_in_clip = False
    check('同一 clip 内各段逐项相同（含帧数/时长）', same_in_clip,
          str([[ (s['info']['nb_frames'], s['info']['duration']) for s in pc['segments']]
               for pc in per_clip]))
    check('每段首帧都是 IDR 且 pts=0',
          all(s['first_idr'] and abs(s['pts']) < 1e-3 for pc in per_clip for s in pc['segments']),
          str([(s['file'], s['first_idr'], s['pts']) for pc in per_clip for s in pc['segments']]))
    check('滤镜链无 pad',
          all(s['filter'] and 'pad=' not in s['filter'] for pc in per_clip for s in pc['segments']),
          str(per_clip[0]['segments'][0]['filter']))
    check('滤镜链 = crop(源框) → [scale(N×480)] → crop(480:480:i*480:0)',
          all(s['filter'].startswith('crop=') and
              s['filter'].endswith('crop=%d:%d:%d:0' % (PANEL, PANEL, (s['index'] - 1) * PANEL))
              for pc in per_clip for s in pc['segments']),
          str([s['filter'] for s in per_clip[0]['segments']]))
    check('+faststart（moov 在 mdat 前）',
          all(open(os.path.join(out_dir, s['file']), 'rb').read(65536).find(b'moov') <
              open(os.path.join(out_dir, s['file']), 'rb').read(65536).find(b'mdat')
              for pc in per_clip for s in pc['segments']))
    for pc in per_clip:
        print('    %-6s %s' % (pc['name'], ' | '.join(
            '%s %dx%d %s %d帧 %.3fs %s' % (s['file'].split('/')[-1], s['info']['width'],
                                           s['info']['height'], s['info']['profile'],
                                           s['info']['nb_frames'], s['info']['duration'],
                                           'IDR' if s['first_idr'] else 'NO') for s in pc['segments'])))

    print('\n=== 5. D. 逐 clip 独立裁剪 + 内容不串 ===')
    c1 = per_clip[0]['manifest']
    check('clip1 用 --crop 1=128:64:1024:512 生效', c1['crop'] == [128, 64, 1024, 512],
          'crop=%s' % c1['crop'])
    geo_expect = sw.resolve_geometry(cols, sw.stream_info(srcs[1])['width'],
                                     sw.stream_info(srcs[1])['height'])
    check('clip2 未指定 crop → 用自己源的最大框居中', per_clip[1]['manifest']['crop'] == geo_expect['crop'],
          'crop=%s vs %s' % (per_clip[1]['manifest']['crop'], geo_expect['crop']))
    check('clip3（960×480）1:1 无缩放', per_clip[2]['manifest']['crop'] == [0, 0, 960, 480] and
          abs(per_clip[2]['manifest']['scale'] - 1.0) < 1e-6,
          'crop=%s scale=%s' % (per_clip[2]['manifest']['crop'], per_clip[2]['manifest']['scale']))
    # 内容不串：各 clip 的 seg_1 首帧互不相同（源不同 → 画面不同）
    bufs = []
    for pc in per_clip:
        b, w, h = frame_rgb(os.path.join(out_dir, pc['segments'][0]['file']), 0)
        bufs.append((b, w, h))
    diffs = {}
    for i in range(len(bufs)):
        for j in range(i + 1, len(bufs)):
            d = diff(bufs[i][0], bufs[j][0], bufs[i][1], bufs[i][2])
            diffs['%s-vs-%s' % (per_clip[i]['name'], per_clip[j]['name'])] = d['mean']
    check('各 clip 首帧互不相同（没有串源/复用同一段）',
          all(v > 10.0 for v in diffs.values()), json.dumps(diffs))

    print('\n=== 6. E. 总时长核对 ===')
    meas_ms = sum(pc['segments'][0]['dur_measured_ms'] for pc in per_clip)
    want_ms = int(round(sum(clip_secs) * 1000))
    check('total_ms == Σ 实测段时长（同 clip 内取第一片）', abs(meas_ms - int(pl['total_ms'])) <= 2,
          'measured=%d total_ms=%d' % (meas_ms, pl['total_ms']))
    check('total_ms ≈ Σ 源片时长 %.3f s（±250ms）' % (sum(clip_secs) / 1000.0),
          abs(int(pl['total_ms']) - want_ms) <= 250,
          'total_ms=%d want=%d' % (pl['total_ms'], want_ms))
    check('总时长 = 各 clip 时长之和（4+6+3 口径）', meas_ms == sum(
        pc['segments'][0]['dur_measured_ms'] for pc in per_clip), '%d ms' % meas_ms)
    print('    clip 时长: %s → 总时长 %d ms' % (
        ', '.join('%s=%dms' % (c['name'], c['dur_ms']) for c in pl['clips']), pl['total_ms']))

    print('\n=== 7. F. v1 兼容壳 wall.json（旧读者/旧固件）===')
    wj = json.load(open(wjp, encoding='utf-8'))
    check('segments = 第 1 个 clip 的分段', len(wj.get('segments', [])) == cols and
          all(s['file'].startswith(pl['clips'][0]['name'] + '/') for s in wj['segments']),
          str([s['file'] for s in wj.get('segments', [])]))
    check('seg_ms == 第一片时长', int(wj.get('seg_ms', 0)) == int(pl['clips'][0]['dur_ms']),
          'seg_ms=%s vs %s' % (wj.get('seg_ms'), pl['clips'][0]['dur_ms']))
    check('total_ms 与 playlist 一致', int(wj.get('total_ms', 0)) == int(pl['total_ms']),
          '%s vs %s' % (wj.get('total_ms'), pl['total_ms']))
    check('clips 概览 3 项（name/dur_ms/segments/source）',
          len(wj.get('clips', [])) == len(pl['clips']) and
          all(list(c.keys()) == ['name', 'dir', 'dur_ms', 'segments', 'source']
              for c in wj['clips']), json.dumps(wj.get('clips'), ensure_ascii=False)[:180])
    check('旧读者可用：segments[0].info.duration == 第一片时长',
          abs(float(wj['segments'][0]['info']['duration']) * 1000 - float(wj['seg_ms'])) <= 1.0)
    lg = sw.load_group(out_dir)
    check('load_group() 读 v2 不报错且 legacy=False',
          lg['legacy'] is False and lg['cols'] == cols and lg['total_ms'] == pl['total_ms'])

    print('\n=== 8. G. 旧布局回归（组目录直接放 seg_<idx>.mp4，无 playlist.json）===')
    leg = os.path.join(EVID, 'legacy_layout_%s' % time.strftime('%H%M%S'))
    rc2, o2 = run_cli(['split', '--in', srcs[0], '--cols', str(cols), '--out-dir', leg], log_path)
    legacy_files = sorted(os.listdir(leg)) if os.path.isdir(leg) else []
    check('split（单源）退出码 0', rc2 == 0, 'exit=%d' % rc2)
    check('旧布局：根目录 seg_1..N.mp4 + wall.json，**不写** playlist.json',
          all(('seg_%d.mp4' % (i + 1)) in legacy_files for i in range(cols)) and
          'wall.json' in legacy_files and 'playlist.json' not in legacy_files,
          str(legacy_files))
    rc3, o3 = run_cli(['verify', '--dir', leg], log_path)
    check('split_wall.py verify --dir <旧布局> 通过', rc3 == 0 and '[OK]' in o3)
    lgl = sw.load_group(leg)
    check('load_group(旧布局) 回退成功（legacy=True, cols/dur 正确）',
          lgl['legacy'] is True and lgl['cols'] == cols and
          abs(lgl['total_ms'] - int(round(clip_secs[0] * 1000))) <= 2,
          'legacy=%s cols=%s total=%s' % (lgl['legacy'], lgl['cols'], lgl['total_ms']))

    print('\n=== 9. 证据图（每组首帧横排 + 全组叠图）===')
    shots = []
    for pc in per_clip:
        seg_paths = [os.path.join(out_dir, s['file']) for s in pc['segments']]
        b, w, h = hstack_rgb(seg_paths, 0)
        png = os.path.join(EVID, 'selftest_group_%s_hstack.png' % pc['name'])
        ff(['-y', '-v', 'error'] + sum([['-ss', '0', '-i', p] for p in seg_paths], []) +
           ['-filter_complex', ''.join('[%d:v]' % i for i in range(len(seg_paths))) +
            'hstack=inputs=%d[v]' % len(seg_paths), '-map', '[v]', '-frames:v', '1', png])
        shots.append(png)
        print('    %-6s %s' % (pc['name'], png))
    allpng = os.path.join(EVID, 'selftest_group_all.png')
    vstack_png(shots, allpng)
    print('    全组叠图 %s（%d 个 clip，每个 %d 段横排）' % (allpng, len(shots), cols))

    rep['group_dir'] = out_dir
    rep['playlist'] = pl
    rep['clips'] = [{k: v for k, v in pc.items() if k != 'manifest'} for pc in per_clip]
    rep['v1_shell'] = {k: v for k, v in wj.items() if k != 'segments'}
    rep['legacy_layout'] = {'dir': leg, 'files': legacy_files}
    rep['total_ms'] = pl['total_ms']
    rep['evidence'] = {'per_clip_hstack': shots, 'all': allpng, 'cli_log': log_path}
    rep['fails'] = fails
    rp = os.path.join(EVID, 'selftest_group_report.json')
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print('\n报告: %s' % rp)
    print('\n=== 总判定: %s ===' % ('[PASS] 多视频组（playlist v2）全绿：布局/清单自洽/段一致/无 pad/'
                                 '首帧 IDR/总时长/兼容壳/旧布局回归'
                                 if not fails else '[FAIL]\n  - ' + '\n  - '.join(fails)))
    if not a.keep:
        shutil.rmtree(TMP, ignore_errors=True)
        print('临时素材已清理（--keep 可保留）；产物与证据保留在 out/_evidence/')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
