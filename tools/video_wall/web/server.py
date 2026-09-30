#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多屏拼接 · 网页工具后端（零依赖）
- 导入视频（上传/选本地路径）→ 预览铺整幅视频，上面叠 N 个相邻 480×480 绿框
- 交互：**拖绿框组**（改裁剪原点）/ **滚轮或缩放条**（改框组大小）；视频固定不动；
  框组被钳制在视频内 → 永远不会出现黑边。**没有"缝"、没有橙色斜纹、没有丢弃区标注。**
- 导出：`crop(源裁剪矩形) → scale(N×480 × 480) → crop(480:480:i*480:0)`，**不出现 pad**；
        `crop` 由前端唯一函数算出并**原样使用**（后端不再用 scale/ox/oy 反推，避免两套映射打架），
         切出 seg_1..N.mp4 (480x480，参数一致、首帧 IDR) + wall.json
- **2026-09-27 v2（多视频轮播组）**：网页可排队多个视频（= 多个 clip，每个可改名/上下移/删除，
        各自摆框、长短不限），组名可自定义 → 一次导出产出整组：
        `c1/seg_1..N.mp4、c2/seg_1..N.mp4 …` + `playlist.json`（v2 清单）+ `wall.json`（v1 兼容壳）；
        分段卡片按 clip 分组显示；「一键分发」走**整组递归推送**（含 playlist.json）。
        · `/api/split` 保留旧语义（单视频 → 根目录 seg_i.mp4 + wall.json，v1 布局，不写 playlist.json）
- 设备：扫描（复用 distribute.scan）/ 手填 IP → 一键分发到对应屏幕（复用 distribute 的 push 逻辑）
         · `/api/push` 可带 `clear_wall`（推送前先清空设备上的旧拼接素材）
         · `/api/clear` 清空设备上的视频素材：scope=wall|video|album|all，`dry_run` 只看不删
         · `/api/drop_group` 删掉一个**已导出的分组**（整目录：cN/seg_i.mp4 + playlist.json + wall.json），
           `dry_run` 只看不删；`_src` 与越界名字一律拒绝
- **2026-09-28 v3（每屏独立窗口）**：网页可**每屏各自拖动**（相邻两屏之间可留「缝」）→
        每 clip 传 `frames=[[x,y,w,h]×N]`；缝=0 且连着摆时（regular）后端自动等价回旧单框口径。

用法：  python server.py --port 8796 --host 0.0.0.0
页面：  http://127.0.0.1:8796/
"""
import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)                       # tools/video_wall
sys.path.insert(0, TOOLS)
import split_wall  # noqa: E402
import distribute  # noqa: E402

OUT = os.path.join(TOOLS, 'out')
SRC = os.path.join(OUT, '_src')
PANEL = 480
os.makedirs(SRC, exist_ok=True)


def ff(*args, timeout=1800):
    p = subprocess.run(['ffmpeg'] + list(args), capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace')[-1500:])
    return p.stdout


def probe(path):
    return split_wall.stream_info(path)


def frame_png(path, t=0.0, w=0):
    """抽一帧 → PNG bytes（可指定宽度缩放）"""
    args = ['-v', 'error', '-ss', str(t), '-i', path, '-frames:v', '1']
    if w:
        args += ['-vf', 'scale=%d:-2' % w]
    args += ['-f', 'image2pipe', '-vcodec', 'png', '-']
    return ff(*args, timeout=120)


# ── 裁剪分割（2026-09-27 口径③：绿框 = 唯一裁剪窗口；无缝、无 pad、无黑边）────
# 几何/滤镜/编码全部复用 split_wall（CLI 与网页同一套算法，结果可互相复现）：
#   crop(源裁剪矩形) → scale(N×480 × 480) → crop(每格 480×480)
# 单一事实源 = 前端算出的 `crop=[x,y,w,h]`（源像素，w = N×h）：后端**原样使用**，
# 只做偶数对齐 + 钳制（与前端同一个 align_crop 规则），并把真正生效的矩形回给前端显示。
PROBE_CACHE = {}            # (路径, 大小, mtime) → stream_info（列表里显示分辨率/时长用）


def read_playlist_file(group, with_files=False):
    """读已导出分组的 playlist.json（v2）；没有 → None（旧 v1 布局）"""
    p = os.path.join(OUT, group, split_wall.PLAYLIST_NAME)
    if not os.path.exists(p):
        return None
    try:
        pl = json.loads(io.open(p, encoding='utf-8').read())
    except Exception:
        return None
    if with_files:
        for c in pl.get('clips', []):
            for s in c.get('segments', []):
                fp = os.path.join(OUT, group, s.get('file', ''))
                try:
                    s['exists'] = os.path.isfile(fp)
                    s['bytes'] = os.path.getsize(fp) if s['exists'] else 0
                except OSError:
                    s['exists'] = False
                    s['bytes'] = 0
    return pl


def probe_cached(path):
    try:
        st = os.stat(path)
        key = (path, st.st_size, int(st.st_mtime))
    except OSError:
        return None
    if key not in PROBE_CACHE:
        try:
            PROBE_CACHE[key] = probe(path)
        except Exception:
            return None
        if len(PROBE_CACHE) > 64:
            PROBE_CACHE.pop(next(iter(PROBE_CACHE)))
    return PROBE_CACHE[key]


def compose_and_split(src, cols, crop, out_name):
    """返回 (out_dir, geo_or_manifest, err)；err 非空时未导出（crop 非法 / 源太小）"""
    info = probe(src)
    geo = split_wall.resolve_geometry(cols, info['width'], info['height'], crop=crop)
    if not geo['valid']:
        if geo['too_small']:
            return None, geo, ('源视频 %d×%d 比单屏 %d×%d 还小，无法保证 1:1 清晰度；'
                               '请换更高分辨率素材' % (geo['src_w'], geo['src_h'], PANEL, PANEL))
        return None, geo, ('裁剪矩形非法：crop=%s（须在源内，且宽 = N×高 = %d×高）'
                           % (geo['crop'], cols))
    out_dir = os.path.join(OUT, out_name)
    man = split_wall.encode_segments(src, geo, out_dir, quiet=True)
    for s in man.get('segments', []):               # 段文件大小（网页卡片显示用）
        try:
            s['bytes'] = os.path.getsize(os.path.join(out_dir, s['file']))
        except OSError:
            s['bytes'] = 0
    return out_dir, man, None


# ── v2：一个组 = 多个视频（clip）轮播；导出整组（c1..cK + playlist.json + wall.json）──
def resolve_clip_src(file):
    f = str(file or '')
    return f if os.path.isabs(f) else os.path.join(SRC, os.path.basename(f))


def clip_error(clip, src, geo, cols):
    """逐 clip 预检的错误文案（None = 没问题）"""
    who = '第 %s 个视频（%s）' % (clip.get('no'), clip.get('name') or os.path.basename(src))
    if not os.path.exists(src):
        return '%s 不存在：%s' % (who, src)
    if geo['too_small']:
        return ('%s：源 %d×%d 小于单屏 %d×%d，无法生成 1:1 的 480×480 分段；请换更高分辨率素材'
                % (who, geo['src_w'], geo['src_h'], PANEL, PANEL))
    if not geo['aspect_ok']:
        return ('%s：裁剪矩形宽 ≠ N×高（N=%d）→ crop=%s；每段是 480×480，所以框组宽必须是 N 倍高'
                % (who, cols, geo['crop']))
    if not geo['inside']:
        return '%s：裁剪矩形越界（crop=%s，源 %d×%d）' % (who, geo['crop'], geo['src_w'], geo['src_h'])
    return None


def compose_group(clips, cols, group_name, out_name):
    """整组导出。返回 (result, err)；err 非空时**不留下任何目录**。"""
    if not clips:
        return None, '队列里还没有视频'
    cols = max(1, int(cols or 2))
    group_name = split_wall.sanitize_group_name(
        group_name, fallback=os.path.splitext(os.path.basename(resolve_clip_src(clips[0].get('file'))))[0])
    srcs, crops, frames, names = [], [], [], []
    for i, c in enumerate(clips, 1):
        c = dict(c or {})
        src = resolve_clip_src(c.get('file'))
        crop = c.get('crop')
        if crop is not None:
            if not isinstance(crop, (list, tuple)) or len(crop) != 4:
                return None, '第 %d 个视频的 crop 必须是 [x,y,w,h]（源像素）' % i
            crop = [float(v) for v in crop]
        fr = c.get('frames')                       # 每屏一个独立窗口（可留缝）
        if fr is not None:
            if (not isinstance(fr, (list, tuple)) or len(fr) != int(cols)
                    or any(not isinstance(f, (list, tuple)) or len(f) != 4 for f in fr)):
                return None, ('第 %d 个视频的 frames 必须是 N=%d 个 [x,y,w,h]（每屏一个窗口）'
                              % (i, int(cols)))
            fr = [[float(v) for v in f] for f in fr]
        if not os.path.exists(src):
            return None, '第 %d 个视频不存在：%s' % (i, src)
        info = probe(src)
        try:
            geo = split_wall.resolve_geometry(cols, info['width'], info['height'],
                                              crop=crop, frames=fr)
        except ValueError as e:
            return None, '第 %d 个视频（%s）：%s' % (i, os.path.basename(src), e)
        bad = clip_error({'no': i, 'name': c.get('name')}, src, geo, cols)
        if bad:
            return None, bad
        srcs.append(src)
        crops.append(crop)
        frames.append(fr)
        names.append(c.get('name'))
    out_dir = os.path.join(OUT, out_name)
    try:
        res = split_wall.group_encode(srcs, cols, out_dir, group=group_name, crops=crops,
                                      names=names, quiet=True, frames=frames)
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)     # 失败不留半成品
        return None, str(e)
    return res, None


# ── HTTP ────────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, 'application/json; charset=utf-8',
                   json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ('/', '/index.html'):
                return self._send(200, 'text/html; charset=utf-8',
                                  io.open(os.path.join(HERE, 'index.html'), encoding='utf-8').read())
            if u.path == '/api/scan':
                rows = distribute.scan(type('A', (), {'subnet': q.get('subnet', ['192.168.1.'])[0]})())
                return self._json({'ok': True, 'devices': [
                    {'ip': r[0], 'model': r[1], 'panel_id': r[2], 'has_wall': r[3], 'so': r[4]}
                    for r in rows]})
            if u.path == '/api/frame':        # 抽帧（源片预览 / 分段缩略图）
                f = q['file'][0]
                if not os.path.isabs(f):
                    # 相对路径先按已导入源片解，再按已导出分组解（如 g2_113221/seg_1.mp4）
                    cand = [os.path.join(SRC, f), os.path.join(OUT, f)]
                    f = next((c for c in cand if os.path.exists(c)), cand[0])
                t = float(q.get('t', ['0'])[0])
                w = int(q.get('w', ['0'])[0])
                return self._send(200, 'image/png', frame_png(f, t, w))
            if u.path == '/api/info':         # 源分辨率等信息（?src= 自动加载/脚本化用）
                f = q.get('src', [''])[0]
                p = f if os.path.isabs(f) else os.path.join(SRC, os.path.basename(f))
                if not os.path.exists(p):
                    return self._json({'ok': False, 'error': 'not found: %s' % f}, 404)
                return self._json({'ok': True, 'file': os.path.basename(p),
                                   'info': probe(p)})
            if u.path == '/api/list':         # 已导入的源片（带分辨率/时长/大小，供列表直接点选）
                fs = []
                for f in sorted(os.listdir(SRC)):
                    p = os.path.join(SRC, f)
                    if not os.path.isfile(p):
                        continue
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = 0
                    fs.append({'name': f, 'bytes': size, 'info': probe_cached(p)})
                return self._json({'ok': True, 'files': fs})
            if u.path == '/api/manifest':     # 读某个已导出分组的 wall.json（重新分发用）
                g = os.path.basename(q.get('group', [''])[0])
                mp = os.path.join(OUT, g, 'wall.json')
                if not g or not os.path.exists(mp):
                    return self._json({'ok': False, 'error': 'not found: %s' % g}, 404)
                man = json.loads(io.open(mp, encoding='utf-8').read())
                man['group'] = g
                for s in man.get('segments', []):
                    try:
                        s['bytes'] = os.path.getsize(os.path.join(OUT, g, s['file']))
                    except OSError:
                        s['bytes'] = 0
                pl = read_playlist_file(g)
                return self._json({'ok': True, 'group': g, 'manifest': man, 'playlist': pl})
            if u.path == '/api/playlist':      # 读整组 v2 清单（含每 clip 段文件是否存在/大小）
                g = os.path.basename(q.get('group', [''])[0])
                if not g or not os.path.exists(os.path.join(OUT, g)):
                    return self._json({'ok': False, 'error': 'not found: %s' % g}, 404)
                pl = read_playlist_file(g, with_files=True)
                if pl is None:
                    return self._json({'ok': False, 'error': '该分组没有 playlist.json（旧 v1 布局）',
                                       'legacy': True, 'group': g}, 404)
                return self._json({'ok': True, 'group': g, 'playlist': pl})
            if u.path == '/favicon.ico':
                return self._send(204, 'image/x-icon', b'')
            if u.path == '/api/out':          # 已导出的分组
                gs = [d for d in os.listdir(OUT) if os.path.isdir(os.path.join(OUT, d))
                      and d != '_src' and os.path.exists(os.path.join(OUT, d, 'wall.json'))]
                gs.sort()
                info = []
                for d in gs:
                    pl = read_playlist_file(d)
                    info.append({'name': d, 'v2': pl is not None,
                                 'group_name': (pl or {}).get('group'),
                                 'clips': (pl or {}).get('n'), 'cols': (pl or {}).get('cols'),
                                 'total_ms': (pl or {}).get('total_ms')})
                return self._json({'ok': True, 'groups': gs, 'info': info})
            if u.path == '/api/download':     # 下载某段（支持 c1/seg_1.mp4 这样的相对子路径）
                g = os.path.basename(q['group'][0])
                rel = q['file'][0].replace('\\', '/')
                root = os.path.normpath(os.path.join(OUT, g))
                p = os.path.normpath(os.path.join(root, rel))
                if not (p == root or p.startswith(root + os.sep)) or not os.path.isfile(p):
                    return self._json({'ok': False, 'error': 'not found'}, 404)
                return self._send(200, 'video/mp4', io.open(p, 'rb').read())
            return self._json({'ok': False, 'error': 'unknown: %s' % u.path}, 404)
        except Exception as e:
            return self._json({'ok': False, 'error': str(e)}, 500)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        ln = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(ln) if ln else b''
        try:
            if u.path == '/api/upload':
                name = urllib.parse.unquote(self.headers.get('X-Filename', 'source.mp4'))
                name = re.sub(r'[^\w\.\-\u4e00-\u9fff]', '_', name)
                p = os.path.join(SRC, name)
                io.open(p, 'wb').write(raw)
                return self._json({'ok': True, 'file': name, 'info': probe(p)})
            body = json.loads(raw.decode('utf-8')) if raw else {}
            if u.path == '/api/split':
                src = body['file']
                if not os.path.isabs(src):
                    src = os.path.join(SRC, os.path.basename(src))
                cols = int(body.get('cols') or 2)
                crop = body.get('crop')
                if not crop or len([v for v in crop]) != 4:
                    return self._json({'ok': False, 'error': 'crop 必须是 [x,y,w,h]（源像素）'}, 400)
                name = 'g%s_%s' % (cols, time.strftime('%H%M%S'))
                d, man, err = compose_and_split(src, cols, crop, name)
                if err:
                    # crop 非法/源太小：明确回标识，前端高亮提示（不会生成任何目录）
                    return self._json({'ok': False, 'error': err,
                                       'crop_requested': man.get('crop_requested'),
                                       'crop_effective': man.get('crop'),
                                       'valid': man.get('valid'),
                                       'too_small': man.get('too_small'),
                                       'aspect_ok': man.get('aspect_ok')})
                return self._json({'ok': True, 'group': os.path.basename(d),
                                   'crop_requested': man['crop_requested'],
                                   'crop_effective': man['crop'],
                                   'manifest': man})
            if u.path == '/api/group_split':    # v2：多个视频（可各自摆框）→ 整组导出
                clips = body.get('clips') or []
                cols = int(body.get('cols') or 2)
                name = 'g%s_%s' % (cols, time.strftime('%H%M%S'))
                if body.get('out_name'):
                    name = re.sub(r'[^\w\.\-]', '_', str(body['out_name']))[:40]
                res, err = compose_group(clips, cols, body.get('group_name'), name)
                if err:
                    return self._json({'ok': False, 'error': err})
                return self._json({'ok': True, 'group': os.path.basename(res['out_dir']),
                                   'group_name': res['group'], 'cols': res['cols'],
                                   'n': res['n'], 'total_ms': res['total_ms'],
                                   'clips': res['clips'], 'playlist': res['playlist'],
                                   'wall': {k: v for k, v in res['wall'].items()
                                            if k not in ('segments',)}})
            if u.path == '/api/push':
                grp = os.path.basename(body['group'])
                seg_dir = os.path.join(OUT, grp)
                devices = body['devices']      # [{ip, idx}]
                n = len(devices)
                group_name = body.get('group_name') or grp
                clear_wall = bool(body.get('clear_wall'))     # 推送前先清掉旧拼接素材
                is_group = bool(body.get('group_dir')) or os.path.exists(
                    os.path.join(seg_dir, 'playlist.json'))
                res = []
                for i, dv in enumerate(devices):
                    dev = '%s:5555' % dv['ip']
                    distribute.adb('connect', dev, timeout=10)
                    try:
                        if is_group:
                            distribute.push_group_one(dev, int(dv.get('idx') or i + 1), n,
                                                      group_name, seg_dir, master=(i == 0),
                                                      clear_wall=clear_wall)
                        else:
                            distribute.push_one(dev, int(dv.get('idx') or i + 1), n,
                                                group_name, seg_dir, master=(i == 0))
                        res.append({'ip': dv['ip'], 'ok': True, 'mode': 'group' if is_group else 'legacy'})
                    except Exception as e:
                        res.append({'ip': dv['ip'], 'ok': False, 'error': str(e)})
                return self._json({'ok': True, 'results': res, 'mode': 'group' if is_group else 'legacy'})
            if u.path == '/api/clear':       # 清空设备上的视频素材（拼接/屏保/相册/全部）
                ips = body.get('devices') or []
                scope = str(body.get('scope') or 'wall')
                dry = bool(body.get('dry_run'))
                if scope not in distribute.CLEAR_TARGETS:
                    return self._json({'ok': False, 'error': 'scope 只能是 %s'
                                       % ' / '.join(distribute.CLEAR_TARGETS)}, 400)
                res = []
                for ip in ips:
                    dev = '%s:5555' % ip
                    distribute.adb('connect', dev, timeout=10)
                    try:
                        rep = distribute.clear_device(dev, scope, dry=dry, quiet=True)
                        res.append({'ip': ip, 'ok': True, 'dry': dry, 'cleared': rep['cleared'],
                                    'before': rep['before'], 'after': rep.get('after')})
                    except Exception as e:
                        res.append({'ip': ip, 'ok': False, 'error': str(e)})
                return self._json({'ok': True, 'scope': scope, 'dry': dry, 'devices': res})
            if u.path == '/api/drop':        # 从导入目录删掉一个源片
                name = os.path.basename(body.get('file', ''))
                p = os.path.join(SRC, name)
                if not name or not os.path.exists(p):
                    return self._json({'ok': False, 'error': 'not found: %s' % name}, 404)
                os.remove(p)
                return self._json({'ok': True})
            if u.path == '/api/drop_group':  # 删掉一个已导出的分组（整个目录：段文件 + playlist.json + wall.json）
                g = os.path.basename(str(body.get('group') or ''))
                d = os.path.normpath(os.path.join(OUT, g))
                if (not g or g == '_src' or not os.path.isdir(d)
                        or not d.startswith(os.path.normpath(OUT) + os.sep)):
                    return self._json({'ok': False, 'error': 'not found: %s' % g}, 404)
                n, nb = 0, 0
                for root, _dirs, fs in os.walk(d):
                    for fn in fs:
                        n += 1
                        try:
                            nb += os.path.getsize(os.path.join(root, fn))
                        except OSError:
                            pass
                if body.get('dry_run'):
                    return self._json({'ok': True, 'dry_run': True, 'group': g,
                                       'files': n, 'bytes': nb})
                shutil.rmtree(d)
                return self._json({'ok': True, 'group': g, 'files': n, 'bytes': nb,
                                   'removed': not os.path.exists(d)})
            if u.path == '/api/reveal':      # 在资源管理器里打开输出目录（本机工具）
                g = os.path.basename(body.get('group', ''))
                d = OUT if not g else os.path.join(OUT, g)
                if not os.path.isdir(d):
                    return self._json({'ok': False, 'error': 'not found: %s' % d}, 404)
                try:
                    if os.name == 'nt':
                        os.startfile(d)      # noqa: S606
                    else:
                        subprocess.Popen(['xdg-open', d])
                except Exception as e:
                    return self._json({'ok': False, 'error': str(e)}, 500)
                return self._json({'ok': True, 'dir': d})
            if u.path == '/api/status':
                devs = body['devices']
                out = []
                for ip in devs:
                    dev = '%s:5555' % ip
                    distribute.adb('connect', dev, timeout=10)
                    prefs = distribute.sh(dev, 'cat /data/preferences.json')
                    cfg = {}
                    for k in distribute.KEYS:
                        m = re.search('"%s"\\s*:\\s*("([^"]*)"|[^,}\\s]+)' % k, prefs)
                        cfg[k] = m.group(1) if m else '-'
                    log = distribute.sh(dev, 'logcat -d -v time')
                    plays = [l.strip()[-80:] for l in log.splitlines() if 'screensaver play[' in l][-2:]
                    out.append({'ip': ip, 'cfg': cfg,
                                'state': distribute.sh(dev, 'getprop sys.zkapp.state').strip(),
                                'plays': plays})
                return self._json({'ok': True, 'devices': out})
            return self._json({'ok': False, 'error': 'unknown: %s' % u.path}, 404)
        except Exception as e:
            return self._json({'ok': False, 'error': str(e)}, 500)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8796)
    ap.add_argument('--host', default='127.0.0.1')
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print('多屏拼接网页工具: http://%s:%d/' % (a.host if a.host != '0.0.0.0' else '127.0.0.1', a.port))
    srv.serve_forever()
