#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_api_crop.py — 网页后端（server.py）绿框裁剪流程冒烟测试

自己在 8797 端口起一份临时 server 实例（不动生产端口），用真实 HTTP 请求回归：
  1. GET /                        → 200，且是新版交互（拖框/滚轮/框外丢弃），无橙色缝文案、无 CDN 外链
  2. GET /api/info?src=           → 源分辨率
  3. /api/split(crop)             → ok=true；**请求 crop == 生效 crop**（后端不再反推）
                                    每段 480×480、滤镜链无 pad、段首帧 IDR、下载段边缘无黑边
  4. /api/split(crop 越界)         → 钳制在源内（生效 crop 合法、inside=true）
  5. /api/split(crop 宽高比≠N:1)   → ok=false（明确报错，不静默变形）
  6. /api/split(源小于单屏)        → ok=false（明确报错）
  7. /api/list /api/out /api/frame /api/download → 200
  8. /api/group_split(frames：每屏独立窗口 + 40px 缝) → ok=true；窗口原样生效、每段自己 crop→scale、
                                     缝不导出（src_crop = 各屏窗口）、每段 480×480/首帧 IDR
  9. /api/group_split(各屏大小不一致)  → ok=false（明确报错，不静默变形）
 10. /api/clear(非法 scope)          → 400；空设备列表 → ok（不碰设备）
 11. /api/drop_group                → dry_run 只看不删 / 真删掉自建分组目录 / 不存在与 _src → 404
用法： python smoke_api_crop.py [--keep]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import split_wall as sw  # noqa: E402
from selfcheck_crop import edge_stats, ff  # noqa: E402

PORT = 8797
TMP = os.path.join(TOOLS, 'temp_check_api')
BASE = 'http://127.0.0.1:%d' % PORT
fails = []


def get(path, raw=False):
    with urllib.request.urlopen(BASE + path, timeout=300) as r:
        body = r.read()
        return r.status, (body if raw else json.loads(body.decode('utf-8')))


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return r.status, json.loads(r.read().decode('utf-8'))


def check(name, cond, detail=''):
    print('  %s %-56s %s' % ('[OK]  ' if cond else '[FAIL]', name, detail))
    if not cond:
        fails.append('%s %s' % (name, detail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    src = os.path.join(TMP, 'bright_1920x1080.mp4')
    vf = ('drawbox=x=0:y=0:w=1920:h=24:color=0xFF2D2D@1:t=fill,'
          'drawbox=x=0:y=1056:w=1920:h=24:color=0x2DFF8A@1:t=fill,'
          'drawbox=x=0:y=0:w=24:h=1080:color=0xFFD12D@1:t=fill,'
          'drawbox=x=1896:y=0:w=24:h=1080:color=0x2DA8FF@1:t=fill')
    ff(['-y', '-v', 'error', '-f', 'lavfi',
        '-i', 'gradients=s=1920x1080:c0=0x3060C0:c1=0xE0D040:x0=0:y0=0:x1=1920:y1=1080:d=3:r=25',
        '-vf', vf] + sw.enc_args() + [src])
    tiny = os.path.join(TMP, 'tiny_320x240.mp4')
    ff(['-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=s=320x240:r=25:d=1'] +
       sw.enc_args() + [tiny])
    # 放到 server 的导入目录里（/api/split 接受文件名）
    src_dir = os.path.join(TOOLS, 'out', '_src')
    os.makedirs(src_dir, exist_ok=True)
    for p in (src, tiny):
        shutil.copyfile(p, os.path.join(src_dir, os.path.basename(p)))
    names = [os.path.basename(p) for p in (src, tiny)]

    proc = subprocess.Popen([sys.executable, os.path.join(HERE, 'server.py'),
                             '--host', '127.0.0.1', '--port', str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                get('/api/list')
                break
            except Exception:
                time.sleep(0.5)

        print('=== 1. 页面 / 静态 ===')
        with urllib.request.urlopen(BASE + '/', timeout=30) as r:
            html = r.read().decode('utf-8')
        check('GET / = 200', r.status == 200)
        check('新版交互（每屏窗口可独立拖动 / 屏缝 / 框外丢弃）',
              '每屏的绿框可以各自独立拖动' in html and '屏缝' in html and '框外丢弃' in html)
        check('屏缝（拼缝补偿）有输入与实现',
              'id="gap"' in html and 'function applyGap' in html and '缝 ' in html)
        check('无"允许黑边"开关', 'allowBlack' not in html)
        check('前端无 CDN 外链', 'http://' not in html.replace('http://127.0.0.1', '')
              and 'https://' not in html)
        check('导出发的是 frames（每屏窗口 = 单一事实源）',
              'frames:(i===CUR?req' in html.replace(' ', ''))

        print('=== 2. /api/info ===')
        st, ji = get('/api/info?src=' + names[0])
        check('返回源分辨率', st == 200 and ji.get('info', {}).get('width') == 1920,
              json.dumps(ji.get('info', {}), ensure_ascii=False)[:80])

        print('=== 3. /api/split（crop 原样使用）===')
        crop = [128, 66, 1024, 512]          # 非居中、非 1:1 缩放；w = N×h
        _, j = post('/api/split', {'file': names[0], 'cols': 2, 'crop': crop})
        check('ok=true', j.get('ok') is True, str(j.get('error', '')))
        man = j.get('manifest', {})
        check('请求 crop == 生效 crop', list(j.get('crop_requested')) == list(j.get('crop_effective')),
              '%s vs %s' % (j.get('crop_requested'), j.get('crop_effective')))
        check('生效 crop 合法且在源内',
              man.get('crop') == [128, 66, 1024, 512] or list(j['crop_effective']) == [128, 66, 1024, 512],
              'crop=%s' % man.get('crop'))
        check('滤镜链 = crop→scale→crop，无 pad',
              all('pad=' not in s.get('filter', '') for s in man.get('segments', [])) and
              all(s['filter'].startswith('crop=') and s['filter'].endswith('crop=480:480:%d:0' % (i * 480))
                  for i, s in enumerate(man.get('segments', []))),
              man.get('segments', [{}])[0].get('filter', ''))
        check('每段 480×480', all(s['info']['width'] == 480 and s['info']['height'] == 480
                                for s in man.get('segments', [])))
        check('bezel 恒 0 / seam_w 恒 0', man.get('bezel') == 0 and man.get('seam_w') == 0)
        check('首帧全 IDR', all(sw.first_keyframe_pts(os.path.join(TOOLS, 'out', j['group'], s['file']))[0]
                              for s in man.get('segments', [])))
        st, body = get('/api/download?group=%s&file=seg_1.mp4' % j['group'], raw=True)
        p1 = os.path.join(TMP, 'dl_seg_1.mp4')
        open(p1, 'wb').write(body)
        es = edge_stats(p1)
        check('下载段边缘无黑边（最外 2px 平均亮度 ≥60）', min(es.values()) >= 60,
              json.dumps(es, ensure_ascii=False))
        st, png = get('/api/frame?file=%s/seg_1.mp4&w=120&t=0' % j['group'], raw=True)
        check('/api/frame 分段缩略图 = PNG', st == 200 and png[:4] == b'\x89PNG')

        print('=== 4. crop 越界 → 钳制在源内 ===')
        _, j2 = post('/api/split', {'file': names[0], 'cols': 2, 'crop': [1400, 900, 1024, 512]})
        c2 = j2.get('crop_effective', [])
        inside = len(c2) == 4 and c2[0] >= 0 and c2[1] >= 0 and c2[0] + c2[2] <= 1920 and c2[1] + c2[3] <= 1080
        check('已钳制（框组仍完全在源内）', j2.get('ok') is True and inside, 'crop=%s' % c2)

        print('=== 5. crop 宽高比 ≠ N:1 → 拒绝 ===')
        _, j3 = post('/api/split', {'file': names[0], 'cols': 2, 'crop': [0, 0, 1000, 400]})
        check('ok=false 且明确报错', j3.get('ok') is False and 'N' in (j3.get('error') or ''),
              (j3.get('error') or '')[:80])

        print('=== 6. 源小于单屏 → 拒绝导出 ===')
        _, before = get('/api/out')
        _, j4 = post('/api/split', {'file': names[1], 'cols': 2, 'crop': [0, 0, 320, 160]})
        check('ok=false（源 320×240 < 480×480）', j4.get('ok') is False and j4.get('too_small') is True,
              (j4.get('error') or '')[:80])
        _, after = get('/api/out')
        check('失败时不生成任何分组目录', sorted(before.get('groups', [])) == sorted(after.get('groups', [])),
              'before=%d after=%d' % (len(before.get('groups', [])), len(after.get('groups', []))))

        print('=== 7. 其它接口 ===')
        st, j5 = get('/api/list')
        check('/api/list', st == 200 and j5.get('ok') is True)
        st, j6 = get('/api/out')
        check('/api/out', st == 200 and j6.get('ok') is True)

        print('=== 8. /api/group_split（每屏独立窗口 + 屏缝）===')
        # cols=2，两屏各自摆位、中间留 40px 缝（源 1920×1080）
        frames = [[200, 100, 520, 520], [760, 300, 520, 520]]
        _, g = post('/api/group_split', {'clips': [{'file': names[0], 'name': 'g1',
                                                   'frames': frames}],
                                         'cols': 2, 'group_name': 'smoke-frames'})
        check('ok=true', g.get('ok') is True, (g.get('error') or '')[:100])
        c1 = (g.get('clips') or [{}])[0]
        check('后端原样使用每屏窗口', c1.get('frames') == frames, str(c1.get('frames')))
        check('per_screen=true / regular=false', c1.get('per_screen') is True
              and c1.get('regular') is False)
        segs = c1.get('segments') or []
        check('每段 480×480', len(segs) == 2 and all(s['info']['width'] == 480 and
                                                    s['info']['height'] == 480 for s in segs))
        check('每段滤镜 = 自己的 crop→scale（无 pad）',
              all('pad=' not in s['filter'] and s['filter'].startswith(
                  'crop=%d:%d:%d:%d' % (f[3], f[3], f[0], f[1])) for s, f in zip(segs, frames)),
              segs[0]['filter'] if segs else '')
        check('段 src_crop = 各屏自己的窗口', [s['src_crop'] for s in segs] == frames,
              str([s['src_crop'] for s in segs]))
        check('缝宽 40px 记在清单里', int(c1.get('gaps', [0])[0]) == 40, str(c1.get('gaps')))
        check('每段首帧 IDR', all(sw.first_keyframe_pts(
            os.path.join(TOOLS, 'out', g['group'], s['file']))[0] for s in segs))
        # 缝里的源画面确实被丢掉：seg_1 最后一列 ≈ 源 x=719，seg_2 第一列 ≈ 源 x=760
        p2 = os.path.join(TMP, 'dl2_seg_2.mp4')
        st, body = get('/api/download?group=%s&file=g1/seg_2.mp4' % g['group'], raw=True)
        open(p2, 'wb').write(body)
        check('第 2 段下载 OK（边缘无黑边）', st == 200 and min(edge_stats(p2).values()) >= 60,
              json.dumps(edge_stats(p2), ensure_ascii=False))

        print('=== 9. /api/group_split（各屏大小不一致 → 拒绝）===')
        _, g2 = post('/api/group_split', {'clips': [{'file': names[0], 'name': 'g1',
                                                     'frames': [[0, 0, 400, 400],
                                                                [500, 0, 600, 600]]}],
                                          'cols': 2, 'group_name': 'smoke-bad'})
        check('ok=false 且报"大小必须一致"', g2.get('ok') is False
              and '大小必须一致' in (g2.get('error') or ''), (g2.get('error') or '')[:100])

        print('=== 10. /api/clear（scope 校验，不碰设备）===')

        def post_code(path, obj):
            try:
                req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=60) as rr:
                    return rr.status, json.loads(rr.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode('utf-8'))

        st, jc = post_code('/api/clear', {'devices': [], 'scope': 'nope'})
        check('非法 scope → 400 且列出可选值', st == 400 and 'wall' in (jc.get('error') or ''),
              str(jc.get('error'))[:80])
        st, jc = post_code('/api/clear', {'devices': [], 'scope': 'wall', 'dry_run': True})
        check('空设备列表 → ok（不动任何设备）', st == 200 and jc.get('ok') is True
              and jc.get('devices') == [])

        print('=== 11. /api/drop_group（删掉一个已导出的分组）===')
        victim = j['group']                       # 第 3 步自己导出的分组（不动别人的）
        vdir = os.path.join(TOOLS, 'out', victim)
        st, jd = post_code('/api/drop_group', {'group': victim, 'dry_run': True})
        check('dry_run 只看不删（目录还在）', st == 200 and jd.get('dry_run') is True
              and jd.get('files', 0) > 0 and os.path.isdir(vdir),
              'files=%s' % jd.get('files'))
        st, jd = post_code('/api/drop_group', {'group': victim})
        check('真删：目录没了且报回文件数', st == 200 and jd.get('ok') is True
              and jd.get('removed') is True and not os.path.exists(vdir),
              'files=%s bytes=%s' % (jd.get('files'), jd.get('bytes')))
        _, jl = get('/api/out')
        check('已不在 /api/out 列表里', victim not in (jl.get('groups') or []))
        st, jd = post_code('/api/drop_group', {'group': 'no_such_group_xyz'})
        check('不存在的分组 → 404', st == 404 and jd.get('ok') is False)
        st, jd = post_code('/api/drop_group', {'group': '_src'})
        check('_src（导入目录）拒绝删除 → 404', st == 404 and jd.get('ok') is False,
              str(jd.get('error'))[:60])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        if not a.keep:
            shutil.rmtree(TMP, ignore_errors=True)
    print('\n=== 总判定: %s ===' % ('[PASS] 全部通过' if not fails else '[FAIL] %s' % fails))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
